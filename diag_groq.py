"""One raw call to Groq (OpenAI-compatible). Tests key, speed, and tool calling."""
import os, sys, json, time, urllib.request, urllib.error
sys.path.insert(0, "."); import llm   # loads .env
key = os.environ.get("GROQ_API_KEY") or sys.exit("❌ GROQ_API_KEY not set")
URL = "https://api.groq.com/openai/v1/chat/completions"

def call(body):
    req = urllib.request.Request(URL, json.dumps(body).encode(),
          {"Content-Type": "application/json", "Authorization": f"Bearer {key}",
           "User-Agent": "Chronoscope/0.1"})
    t = time.time()
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.load(r), time.time() - t

try:
    # 1. Plain reply
    out, dt = call({"model": "openai/gpt-oss-120b",
                    "messages": [{"role": "user", "content": "Reply with exactly: OK"}]})
    print(f"✅ Plain reply in {dt:.1f}s: {out['choices'][0]['message']['content'].strip()}")

    # 2. Tool calling (what the agent needs)
    tool = {"type": "function", "function": {
        "name": "sky_on_date", "description": "Describe the night sky for a date and city",
        "parameters": {"type": "object", "properties": {
            "date": {"type": "string"}, "city": {"type": "string"}}, "required": ["date"]}}}
    out, dt = call({"model": "openai/gpt-oss-120b", "tools": [tool],
                    "messages": [{"role": "user",
                                  "content": "What did the sky look like in Berlin on 1989-11-09?"}]})
    calls = out["choices"][0]["message"].get("tool_calls") or []
    if calls:
        f = calls[0]["function"]
        print(f"✅ Tool call in {dt:.1f}s: {f['name']}({f['arguments']})")
    else:
        print("⚠️  Model answered without calling the tool")
except urllib.error.HTTPError as e:
    print(f"❌ HTTP {e.code}: {e.read().decode()[:300]}")
