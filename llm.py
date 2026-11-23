"""Shared Gemini helper: newest model first, timeouts, visible retries, fallback."""
import os, re, time
from google import genai
from google.genai import types

TIMEOUT_S = 60          # max wait per request
MAX_TOTAL_S = 240       # give up entirely after this

RETRYABLE = ("500", "503", "504", "429", "unavailable", "deadline",
             "resource_exhausted", "timeout", "timed out", "internal")

def _load_env(path=".env"):
    if os.path.exists(path):
        for line in open(path):
            if "=" in line and not line.startswith("#"):
                k, v = line.strip().split("=", 1)
                os.environ.setdefault(k, v)
_load_env()

_client = None
def client():
    global _client
    if _client is None:
        key = os.environ.get("GEMINI_API_KEY")
        if not key:
            raise RuntimeError("GEMINI_API_KEY not set")
        opts = {"timeout": TIMEOUT_S * 1000}                 # milliseconds
        try:                                                 # turn off SDK's silent retries
            opts["retry_options"] = types.HttpRetryOptions(attempts=1)
        except (AttributeError, TypeError):
            pass                                             # older SDK: no retries anyway
        _client = genai.Client(api_key=key, http_options=types.HttpOptions(**opts))
    return _client

def _version(n):
    m = re.search(r"gemini-(\d+(?:\.\d+)?)", n)
    return float(m.group(1)) if m else 0.0

_models_cache = None
def candidate_models():
    global _models_cache
    if _models_cache is None:
        names = [m.name.replace("models/", "") for m in client().models.list()
                 if "flash" in m.name and "generateContent" in (m.supported_actions or [])
                 and not any(x in m.name for x in ("image", "tts", "live", "audio", "lite"))]
        names.sort(key=lambda n: (_version(n), "preview" not in n), reverse=True)
        saved = os.environ.get("GEMINI_MODEL")
        if saved in names:
            names.remove(saved); names.insert(0, saved)
        _models_cache = names
    return _models_cache

def generate(prompt, retries=0, verbose=False):
    """Return (model_used, text). Times out, retries busy models, falls back."""
    start, last = time.time(), None
    for model in candidate_models():
        for attempt in range(retries + 1):
            if time.time() - start > MAX_TOTAL_S:
                raise RuntimeError(f"Gave up after {MAX_TOTAL_S}s. Last error: {last}")
            if verbose: print(f"   → trying {model} (attempt {attempt + 1})", flush=True)
            try:
                r = client().models.generate_content(model=model, contents=prompt)
                return model, r.text
            except Exception as e:
                msg, last = str(e), e
                if "404" in msg:
                    if verbose: print(f"     retired, next model"); break
                if "429" in msg or "resource_exhausted" in msg.lower():
                    if verbose: print("     quota exhausted for this model, next model")
                    break
                if any(x in msg.lower() for x in RETRYABLE):
                    wait = 3 * (attempt + 1)
                    if verbose: print(f"     busy/timeout, waiting {wait}s")
                    time.sleep(wait); continue
                raise
    raise RuntimeError(f"All Gemini models failed. Last error: {last}")
