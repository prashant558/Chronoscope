"""Checks the provider fallback chain: plain reply + tool calling."""
import sys, json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import llm

provs = llm.available()
if not provs: sys.exit("❌ No provider keys found (GROQ_API_KEY / GEMINI_API_KEY / GITHUB_MODELS_TOKEN)")
print("Providers configured:", ", ".join(p[0] for p in provs))

print("\n1. Plain reply:")
who, text = llm.generate("Reply with exactly: OK", verbose=True)
print(f"✅ {who}: {text.strip()}")

print("\n2. Tool calling:")
tool = {"type": "function", "function": {
    "name": "sky_on_date", "description": "Describe the night sky for a date and city",
    "parameters": {"type": "object", "properties": {
        "date": {"type": "string", "description": "YYYY-MM-DD"},
        "city": {"type": "string"}}, "required": ["date"]}}}
who, msg = llm.chat([{"role": "user", "content": "What was the sky like in Berlin on 9 Nov 1989?"}],
                    tools=[tool], verbose=True)
calls = msg.get("tool_calls") or []
assert calls, f"No tool call from {who}: {msg.get('content')}"
args = json.loads(calls[0]["function"]["arguments"])
assert args.get("date") == "1989-11-09", args
print(f"✅ {who} called {calls[0]['function']['name']}({args})")
print("\n🚀 LLM layer ready for the agent")
