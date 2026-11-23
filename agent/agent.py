"""Chronoscope agent: connects to MCP servers, lets the LLM pick tools, writes a time capsule."""
import asyncio, json, os, sys, time
from contextlib import AsyncExitStack
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import llm
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client, get_default_environment

# server name: (script, env vars it needs). Least privilege: each server gets only its own keys.
SERVERS = {
    "sky":     ("servers/sky_mcp.py", []),
    "history": ("servers/history_mcp.py", []),
    "news":    ("servers/news_mcp.py", ["NYT_API_KEY"]),
}
MAX_STEPS = 8
MAX_TOOL_CHARS = 2000      # keep prompts small: Groq free tier has a tokens-per-minute limit

SYSTEM = """You are Chronoscope, a time-travel research agent. The user gives a date (any format) and maybe a place.

Plan:
1. FIRST reply: call events_on_date AND headlines_on_date together (date as YYYY-MM-DD).
2. SECOND reply: pick the city where the main event happened (call list_cities if unsure; nearest listed city is fine,
   or pass lat/lon/timezone) and call sky_on_date for that evening, or the event time if known.
   Also call article_summary for the main event's Wikipedia article.
3. Then write the capsule. No more tool calls.

Capsule format (Markdown, under 350 words):
## 🗓️ <date>: <short title>
### What happened
### In the newspapers
2-4 REAL headlines about the main event, quoted exactly from the tool result, mark front-page ones with 📰.
Optionally one line 'Also in the news:' with one unrelated front-page headline.
### The sky that night
place, local time, darkness, moon phase, visible planets with direction
### Why it mattered
2-3 sentences

Rules: use ONLY facts from tool results. Never invent headlines or events. If a tool returns an error,
say that section is unavailable. Sky data exists only for 1900-2050; newspapers only from Sept 1851."""


class Agent:
    def __init__(self):
        self.stack, self.tools, self.route = AsyncExitStack(), [], {}

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
                schema = (getattr(t, "input_schema", None) or getattr(t, "inputSchema", None)
                          or {"type": "object", "properties": {}})
                self.tools.append({"type": "function", "function": {
                    "name": t.name, "description": (t.description or "")[:600], "parameters": schema}})
                self.route[t.name] = (name, session)
        return self

    async def __aexit__(self, *exc):
        await self.stack.aclose()

    async def call_tool(self, name, args):
        if name not in self.route:
            return json.dumps({"error": f"Unknown tool '{name}'"})
        _, session = self.route[name]
        try:
            res = await session.call_tool(name, args)
            return "".join(getattr(c, "text", "") for c in res.content)
        except Exception as e:
            return json.dumps({"error": f"{type(e).__name__}: {e}"})

    async def run(self, question, verbose=True):
        messages = [{"role": "system", "content": SYSTEM}, {"role": "user", "content": question}]
        trace, t0 = [], time.time()
        for step in range(1, MAX_STEPS + 1):
            who, msg = await asyncio.to_thread(llm.chat, messages, self.tools, verbose)
            calls = msg.get("tool_calls") or []
            if not calls:                                         # LLM is done → final answer
                return {"answer": msg.get("content") or "", "trace": trace,
                        "model": who, "seconds": round(time.time() - t0, 1)}
            messages.append({"role": "assistant", "content": msg.get("content"), "tool_calls": calls})
            for c in calls:
                fn = c["function"]["name"]
                try:
                    args = json.loads(c["function"].get("arguments") or "{}")
                except json.JSONDecodeError:
                    args = {}
                t = time.time()
                out = await self.call_tool(fn, args)
                server = self.route.get(fn, ("?",))[0]
                trace.append({"step": step, "server": server, "tool": fn, "args": args,
                              "seconds": round(time.time() - t, 2), "chars": len(out),
                              "error": '"error"' in out[:200]})
                if verbose:
                    print(f"🔧 step {step}: {server}.{fn}({json.dumps(args)}) → {len(out)} chars, "
                          f"{time.time()-t:.1f}s")
                messages.append({"role": "tool", "tool_call_id": c["id"], "content": out[:MAX_TOOL_CHARS]})
        # Step limit reached: force a final answer without tools
        messages.append({"role": "user", "content": "Write the final capsule now with what you have."})
        who, msg = await asyncio.to_thread(llm.chat, messages, None, verbose)
        return {"answer": msg.get("content") or "", "trace": trace,
                "model": who, "seconds": round(time.time() - t0, 1)}


async def main():
    question = " ".join(sys.argv[1:]) or "9 November 1989"
    async with Agent() as agent:
        print(f"🔌 Connected. Tools discovered: {', '.join(sorted(agent.route))}\n")
        out = await agent.run(question)
    print("\n" + "═" * 60 + "\n" + out["answer"] + "\n" + "═" * 60)
    print(f"{len(out['trace'])} tool calls · {out['seconds']}s · written by {out['model']}")

if __name__ == "__main__":
    asyncio.run(main())
