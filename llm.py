"""One LLM helper, many free providers (all OpenAI-compatible). Falls back automatically."""
import json, os, time, urllib.request, urllib.error
from pathlib import Path

ROOT = Path(__file__).resolve().parent
def _load_env():
    """Load non-secret settings (e.g. GEMINI_MODEL) from .env. Keys come only from Codespaces secrets."""
    f = ROOT / ".env"
    if f.exists():
        for line in open(f):
            if "=" in line and not line.startswith("#"):
                k, v = line.strip().split("=", 1)
                if not k.endswith(("_KEY", "_TOKEN", "_SECRET")):
                    os.environ.setdefault(k, v)
_load_env()

# Order = priority. (name, base_url, env var holding the key, [models])
PROVIDERS = [
    ("groq", "https://api.groq.com/openai/v1", "GROQ_API_KEY",
     ["openai/gpt-oss-120b", "llama-3.3-70b-versatile"]),
    ("gemini", "https://generativelanguage.googleapis.com/v1beta/openai", "GEMINI_API_KEY",
     [os.environ.get("GEMINI_MODEL", "gemini-3.6-flash")]),
    ("github", "https://models.github.ai/inference", "GITHUB_MODELS_TOKEN",
     ["openai/gpt-4.1-mini"]),
]
TIMEOUT_S = 45

def available():
    return [(n, u, os.environ[k], ms) for n, u, k, ms in PROVIDERS if os.environ.get(k)]

def _post(url, key, body):
    req = urllib.request.Request(f"{url}/chat/completions", json.dumps(body).encode(),
          {"Content-Type": "application/json", "Authorization": f"Bearer {key}",
           "User-Agent": "Chronoscope/0.1"})
    with urllib.request.urlopen(req, timeout=TIMEOUT_S) as r:
        return json.load(r)

def chat(messages, tools=None, verbose=False, temperature=0.3):
    """Returns (provider/model, assistant_message). Message may contain 'tool_calls'."""
    errors = []
    for name, url, key, models in available():
        for model in models:
            body = {"model": model, "messages": messages, "temperature": temperature}
            if tools: body["tools"] = tools
            t = time.time()
            try:
                out = _post(url, key, body)
                if verbose: print(f"   ✓ {name}/{model} in {time.time()-t:.1f}s")
                return f"{name}/{model}", out["choices"][0]["message"]
            except urllib.error.HTTPError as e:
                errors.append(f"{name}/{model}: HTTP {e.code}")
                if verbose: print(f"   ✗ {name}/{model}: HTTP {e.code}, trying next")
            except Exception as e:
                errors.append(f"{name}/{model}: {type(e).__name__}")
                if verbose: print(f"   ✗ {name}/{model}: {type(e).__name__}, trying next")
    raise RuntimeError("All LLM providers failed: " + "; ".join(errors or ["no API keys set"]))

def generate(prompt, verbose=False):
    """Simple text in, text out. Returns (provider/model, text)."""
    who, msg = chat([{"role": "user", "content": prompt}], verbose=verbose)
    return who, msg.get("content") or ""
