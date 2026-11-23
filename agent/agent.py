"""Chronoscope agent: connects to MCP servers, lets the LLM pick tools, writes a verified time capsule."""
import asyncio, json, os, re, sys, time
from contextlib import AsyncExitStack
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import llm
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client, get_default_environment

SERVERS = {   # name: (script, env vars it needs). Least privilege.
    "sky":     ("servers/sky_mcp.py", []),
    "history": ("servers/history_mcp.py", []),
    "news":    ("servers/news_mcp.py", ["NYT_API_KEY"]),
    "knowledge": ("servers/knowledge_mcp.py", []),
}
MAX_STEPS = 5
MAX_TOOL_CHARS = 1800
HIDDEN_FROM_LLM = {"list_cities"}       # called once at startup instead

SYSTEM = """You are Chronoscope, a time-travel research agent. The user gives a date (any format) and maybe a place.

Plan (be efficient, at most 3 rounds of tool calls):
1. Call events_on_date AND headlines_on_date in the SAME reply (date as YYYY-MM-DD).
2. Call sky_on_date for the place of the main event (use the nearest known city below, or lat/lon/timezone)
   AND research(topic=<main event's Wikipedia article title>, question='What happened and why did it matter?'),
   in the SAME reply.
3. Write the capsule. Never call the same tool twice with the same arguments.

Known cities for sky_on_date: {cities}

Capsule format (Markdown, under 350 words):
## 🗓️ <date>: <short title>
### What happened
2-4 sentences. EVERY sentence ends with the [ref] number of the research passage that supports it.
### In the newspapers
2-4 headlines about the main event, copied EXACTLY from headlines_on_date, in “quotes”. Mark front_page ones with 📰.
Optionally one line 'Also in the news:' with one unrelated front-page headline, also copied exactly.
### The sky that night
place, local time, darkness, moon phase, visible planets with direction
### Why it mattered
2-3 sentences, each ending with its [ref]. Do NOT write a Sources section; it is added automatically

STRICT RULES:
- Use ONLY facts that appear in tool results. Do NOT add details from your own memory
  (places, numbers, outcomes), even if you are sure they are true.
- Never write a headline that is not in the headlines_on_date result.
- If a tool returned an error or nothing relevant, say so briefly.
- Sky data exists only for 1900-2050; newspapers only from Sept 1851."""


def _norm(s):
    return re.sub(r"[^a-z0-9 ]", "", s.lower().replace("‘", "'").replace("’", "'"))

def _compact(text):
    """Shrink tool output for the LLM: drop URLs/source, trim long strings."""
    try:
        obj = json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return text[:MAX_TOOL_CHARS]
    def walk(o):
        if isinstance(o, dict):
            return {k: walk(v) for k, v in o.items() if k not in ("url", "source")}
        if isinstance(o, list):
            return [walk(x) for x in o]
        if isinstance(o, str) and len(o) > 220:
            return o[:220] + "…"
        return o
    return json.dumps(walk(obj), ensure_ascii=False, separators=(",", ":"))[:MAX_TOOL_CHARS]

def verify_headlines(answer, known):
    """Remove any quoted headline in the newspaper section that isn't in the real NYT data."""
    known_n = [_norm(h) for h in known]
    out, removed, in_news = [], [], False
    for line in answer.split("\n"):
        if line.startswith("###"):
            in_news = "newspaper" in line.lower()
        quotes = re.findall(r"[“\"]([^”\"]{8,})[”\"]", line) if in_news else []
        if quotes and not all(any(_norm(q)[:40] in k for k in known_n) for q in quotes):
            removed.append(line.strip())
            continue
        out.append(line)
    return "\n".join(out), removed


def attach_sources(answer, sources):
    """Drop citations that don't exist, then append a Sources list built from real passages."""
    answer = re.split(r"\n#+\s*Sources", answer)[0].rstrip()
    valid = {s["ref"] for s in sources}
    used = sorted({int(n) for n in re.findall(r"\[(\d+)\]", answer)})
    for n in used:
        if n not in valid:
            answer = answer.replace(f"[{n}]", "")
    cited = [s for s in sources if s["ref"] in used and s["ref"] in valid]
    if cited:
        def link(s):
            sec = s["section"] or ""
            return s["url"] + ("" if sec in ("", "Introduction") else "#" + sec.replace(" ", "_"))
        answer += "\n\n### Sources\n" + "\n".join(
            f"[{s['ref']}] {s['article']}, {s['section']}: {link(s)}" for s in cited)
    return answer


class Agent:
    def __init__(self):
        self.stack, self.tools, self.route, self.cities = AsyncExitStack(), [], {}, []

    async def __aenter__(self):
        for name, (script, keys) in SERVERS.items():
            missing = [k for k in keys if not os.environ.get(k)]
            if missing:
                raise RuntimeError(f"{name} server needs {missing} (Codespaces secret)")
            env = {**get_default_environment(), **{k: os.environ[k] for k in keys}}
            params = StdioServerParameters(command=sys.executable, args=[str(ROOT / script)], env=env)
            r, w = await self.stack.enter_async_context(stdio_client(params))
            session = await self.stack.enter_async_context(ClientSession(r, w))
            await session.initialize()
            for t in (await session.list_tools()).tools:          # discover tools, don't hard-code
                self.route[t.name] = (name, session)
                if t.name in HIDDEN_FROM_LLM:
                    continue
                schema = (getattr(t, "input_schema", None) or getattr(t, "inputSchema", None)
                          or {"type": "object", "properties": {}})
                self.tools.append({"type": "function", "function": {
                    "name": t.name, "description": (t.description or "")[:500], "parameters": schema}})
        if "list_cities" in self.route:                            # one call at startup, not per run
            try:
                self.cities = json.loads(await self.call_tool("list_cities", {}))
            except Exception:
                self.cities = []
        return self

    async def __aexit__(self, *exc):
        await self.stack.aclose()

    @staticmethod
    def _register_sources(out, sources):
        """Give every retrieved passage a global [ref] number; the LLM only ever sees these refs."""
        try:
            data = json.loads(out)
        except (json.JSONDecodeError, TypeError):
            return out[:MAX_TOOL_CHARS]
        if "error" in data:
            return json.dumps(data)
        passages = []
        for p in data.get("passages", []):
            hit = next((s for s in sources if s["article"] == data.get("article") and s["text"] == p["text"]), None)
            if not hit:
                hit = {"ref": len(sources) + 1, "article": data.get("article"), "section": p.get("section"),
                       "url": data.get("url"), "text": p["text"]}
                sources.append(hit)
            passages.append({"ref": hit["ref"], "section": p.get("section"), "text": p["text"][:700]})
        return json.dumps({"article": data.get("article"), "passages": passages}, ensure_ascii=False)

    def _coerce(self, fn, args):
        """Fix common small-model mistakes: wrong types for arguments."""
        schema = next((t["function"]["parameters"] for t in self.tools
                       if t["function"]["name"] == fn), {})
        props = schema.get("properties", {})
        fixed = {}
        for k, v in args.items():
            types = {props.get(k, {}).get("type")} | {x.get("type") for x in props.get(k, {}).get("anyOf", [])}
            try:
                if "string" in types and not isinstance(v, str): v = str(v)
                elif "integer" in types and isinstance(v, str): v = int(v)
                elif "number" in types and isinstance(v, str): v = float(v)
            except ValueError:
                pass
            fixed[k] = v
        return fixed

    async def call_tool(self, name, args):
        if name not in self.route:
            return json.dumps({"error": f"Unknown tool '{name}'"})
        try:
            res = await self.route[name][1].call_tool(name, args)
            sc = getattr(res, "structured_content", None) or getattr(res, "structuredContent", None)
            if sc is not None:
                if isinstance(sc, dict) and set(sc) == {"result"}:   # MCP wraps non-dict returns
                    sc = sc["result"]
                return json.dumps(sc, ensure_ascii=False)
            texts = [getattr(c, "text", "") for c in res.content]
            if len(texts) > 1:                                        # list returned as many blocks
                return json.dumps(texts, ensure_ascii=False)
            return texts[0] if texts else ""
        except Exception as e:
            return json.dumps({"error": f"{type(e).__name__}: {e}"})

    async def run(self, question, verbose=True):
        system = SYSTEM.format(cities=", ".join(self.cities) if self.cities else "(unknown, use lat/lon)")
        messages = [{"role": "system", "content": system}, {"role": "user", "content": question}]
        trace, memo, headlines, sources, t0 = [], {}, [], [], time.time()
        who = "?"

        for step in range(1, MAX_STEPS + 1):
            who, msg = await asyncio.to_thread(llm.chat, messages, self.tools, verbose)
            calls = msg.get("tool_calls") or []
            if not calls:
                answer = msg.get("content") or ""
                break
            messages.append({"role": "assistant", "content": msg.get("content"), "tool_calls": calls})
            for c in calls:
                fn = c["function"]["name"]
                try:
                    args = json.loads(c["function"].get("arguments") or "{}")
                except json.JSONDecodeError:
                    args = {}
                args = self._coerce(fn, args)
                key = (fn, json.dumps(args, sort_keys=True))
                t, cached = time.time(), key in memo
                out = memo[key] if cached else await self.call_tool(fn, args)
                memo[key] = out
                if fn == "headlines_on_date":
                    try:
                        headlines += [h["headline"] for h in json.loads(out).get("headlines", [])]
                    except Exception:
                        pass
                server = self.route.get(fn, ("?",))[0]
                trace.append({"step": step, "server": server, "tool": fn, "args": args, "cached": cached,
                              "seconds": round(time.time() - t, 2), "error": '"error"' in out[:200]})
                if verbose:
                    print(f"🔧 step {step}: {server}.{fn}({json.dumps(args)})"
                          + (" → reused earlier result" if cached else f" → {len(out)} chars, {time.time()-t:.1f}s"))
                content = self._register_sources(out, sources) if fn == "research" else _compact(out)
                if cached:
                    content = "(Already called with these arguments; same result.) " + content
                messages.append({"role": "tool", "tool_call_id": c["id"], "content": content})
        else:
            messages.append({"role": "user", "content": "Write the final capsule now. No more tool calls."})
            who, msg = await asyncio.to_thread(llm.chat, messages, None, verbose)
            answer = msg.get("content") or ""

        answer, removed = verify_headlines(answer, headlines)
        answer = attach_sources(answer, sources)
        if verbose and removed:
            print(f"🛡️  Guard removed {len(removed)} unverified headline line(s):")
            for r in removed: print(f"     ✂ {r[:100]}")
        return {"answer": answer, "trace": trace, "model": who, "removed_headlines": removed, "sources": sources,
                "seconds": round(time.time() - t0, 1)}


async def main():
    question = " ".join(sys.argv[1:]) or "9 November 1989"
    async with Agent() as agent:
        print(f"🔌 Connected. Tools: {', '.join(sorted(agent.route))} · {len(agent.cities)} cities\n")
        out = await agent.run(question)
    print("\n" + "═" * 60 + "\n" + out["answer"] + "\n" + "═" * 60)
    print(f"{len(out['trace'])} tool calls · {out['seconds']}s · written by {out['model']}"
          + (f" · 🛡️ {len(out['removed_headlines'])} headline(s) removed" if out["removed_headlines"] else ""))

if __name__ == "__main__":
    asyncio.run(main())
