"""One LLM helper, many free providers (OpenAI-compatible). Discovers models, waits on rate limits,
sanitizes tool schemas, falls back automatically."""
import copy, json, os, time, urllib.request, urllib.error
from pathlib import Path

ROOT = Path(__file__).resolve().parent
def _load_env():
    """Non-secret settings only (e.g. GEMINI_MODEL). Keys come from Codespaces secrets."""
    f = ROOT / ".env"
    if f.exists():
        for line in open(f):
            if "=" in line and not line.startswith("#"):
                k, v = line.strip().split("=", 1)
                if not k.endswith(("_KEY", "_TOKEN", "_SECRET")):
                    os.environ.setdefault(k, v)
_load_env()

# (name, base_url, key env var, preferred models; "auto" = discover the rest from /models)
PROVIDERS = [
    ("groq",   "https://api.groq.com/openai/v1", "GROQ_API_KEY",
     ["openai/gpt-oss-120b", "openai/gpt-oss-20b", "auto"]),
    ("gemini", "https://generativelanguage.googleapis.com/v1beta/openai", "GEMINI_API_KEY",
     [os.environ.get("GEMINI_MODEL", "gemini-3.6-flash")]),
    ("github", "https://models.github.ai/inference", "GITHUB_MODELS_TOKEN",
     ["openai/gpt-4.1-mini"]),
]
TIMEOUT_S = 45
MAX_WAIT_S = 30                     # wait this long at most when told "retry after N s"
NOT_CHAT = ("guard", "orpheus", "whisper", "tts", "allam", "compound", "embed", "safeguard")

def _req(url, key, body=None):
    headers = {"Authorization": f"Bearer {key}", "User-Agent": "Chronoscope/0.1"}
    data = None
    if body is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(body).encode()
    with urllib.request.urlopen(urllib.request.Request(url, data, headers), timeout=TIMEOUT_S) as r:
        return json.load(r)

_model_cache = {}
def _models(name, url, key, preferred):
    if name in _model_cache:
        return _model_cache[name]
    models = [m for m in preferred if m != "auto"]
    if "auto" in preferred:
        try:
            ids = sorted(m["id"] for m in _req(f"{url}/models", key)["data"])
            available = [i for i in ids if not any(x in i.lower() for x in NOT_CHAT)]
            models = [m for m in models if m in ids] + [i for i in available if i not in models]
        except Exception:
            pass
    _model_cache[name] = models
    return models

def available():
    return [(n, u, os.environ[k], ms) for n, u, k, ms in PROVIDERS if os.environ.get(k)]

def _clean_schema(s):
    """Make JSON schemas acceptable to strict providers (e.g. Gemini): drop titles, collapse Optional."""
    if isinstance(s, dict):
        s = {k: _clean_schema(v) for k, v in s.items() if k not in ("title", "$schema")}
        if "anyOf" in s:
            non_null = [x for x in s["anyOf"] if x.get("type") != "null"]
            if len(non_null) == 1:
                rest = {k: v for k, v in s.items() if k != "anyOf"}
                rest.pop("default", None) if rest.get("default") is None else None
                s = {**non_null[0], **rest}
        if s.get("default", 0) is None:
            s.pop("default")
        return s
    if isinstance(s, list):
        return [_clean_schema(x) for x in s]
    return s

def _clean_messages(messages):
    out = []
    for m in messages:
        m = {k: v for k, v in m.items() if k in ("role", "content", "tool_calls", "tool_call_id", "name")}
        if m.get("content") is None:
            m["content"] = ""
        out.append(m)
    return out

def chat(messages, tools=None, verbose=False, temperature=0.3):
    """Returns (provider/model, assistant_message). Message may contain 'tool_calls'."""
    msgs = _clean_messages(messages)
    clean_tools = [{"type": "function", "function": {**t["function"],
                    "parameters": _clean_schema(t["function"].get("parameters", {}))}}
                   for t in tools] if tools else None
    errors = []
    for name, url, key, preferred in available():
        for model in _models(name, url, key, preferred):
            body = {"model": model, "messages": msgs, "temperature": temperature}
            if clean_tools: body["tools"] = clean_tools
            for attempt in range(2):
                t = time.time()
                try:
                    out = _req(f"{url}/chat/completions", key, body)
                    if verbose: print(f"   ✓ {name}/{model} in {time.time()-t:.1f}s")
                    return f"{name}/{model}", out["choices"][0]["message"]
                except urllib.error.HTTPError as e:
                    detail = e.read().decode(errors="ignore")[:160].replace("\n", " ")
                    wait = e.headers.get("retry-after")
                    if e.code == 400 and "tool call validation" in detail.lower() and attempt == 0:
                        if verbose: print(f"   ↻ {name}/{model}: malformed tool call, retrying once")
                        continue
                    if e.code == 429 and attempt == 0 and wait and float(wait) <= MAX_WAIT_S:
                        if verbose: print(f"   ⏳ {name}/{model}: rate limit, waiting {float(wait):.0f}s")
                        time.sleep(float(wait) + 0.5)
                        continue
                    errors.append(f"{name}/{model}: HTTP {e.code} {detail}")
                    if verbose: print(f"   ✗ {name}/{model}: HTTP {e.code} {detail[:100]}")
                    break
                except Exception as e:
                    errors.append(f"{name}/{model}: {type(e).__name__}")
                    if verbose: print(f"   ✗ {name}/{model}: {type(e).__name__}")
                    break
    raise RuntimeError("All LLM providers failed:\n  " + "\n  ".join(errors or ["no API keys set"]))

def generate(prompt, verbose=False):
    who, msg = chat([{"role": "user", "content": prompt}], verbose=verbose)
    return who, msg.get("content") or ""
