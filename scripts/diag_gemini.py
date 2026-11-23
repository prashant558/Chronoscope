import sys, pathlib; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))  # repo root
"""One raw REST call to Gemini, no SDK. Tells us: service problem or SDK problem."""
import os, sys, json, time, urllib.request, urllib.error
sys.path.insert(0, "."); import llm  # only for .env loading
key = os.environ.get("GEMINI_API_KEY") or sys.exit("❌ GEMINI_API_KEY not set")
model = os.environ.get("GEMINI_MODEL", "gemini-3.6-flash")
url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
body = json.dumps({"contents": [{"parts": [{"text": "Reply with exactly: OK"}]}]}).encode()
req = urllib.request.Request(url, body, {"Content-Type": "application/json", "x-goog-api-key": key})
t = time.time()
try:
    with urllib.request.urlopen(req, timeout=90) as r:
        out = json.load(r)
    text = out["candidates"][0]["content"]["parts"][0]["text"]
    print(f"✅ Raw REST OK in {time.time()-t:.1f}s: {text.strip()}")
    print("   → Service is fine; if llm.py still hangs, the SDK version is the problem.")
except urllib.error.HTTPError as e:
    print(f"❌ HTTP {e.code} after {time.time()-t:.1f}s: {e.read().decode()[:300]}")
    print("   → 429 = quota still used up; 503/504 = Google overloaded (not your code).")
except Exception as e:
    print(f"❌ {type(e).__name__} after {time.time()-t:.1f}s: {e}")
