"""Find out which GROQ_API_KEY is used and why Groq rejects it. Never prints the full key."""
import os, json, urllib.request, urllib.error

def mask(k): return f"{k[:6]}…{k[-4:]}" if k and len(k) > 10 else repr(k)

def inspect(label, k):
    if not k:
        print(f"   {label}: (not set)"); return
    issues = []
    if k != k.strip():               issues.append("has spaces/newline at start or end")
    if k[:1] in "\"'" or k[-1:] in "\"'": issues.append("wrapped in quotes")
    if not k.strip().strip("\"'").startswith("gsk_"): issues.append("doesn't start with gsk_")
    if "your_key" in k:              issues.append("is the PLACEHOLDER text, not a real key")
    print(f"   {label}: {mask(k)}  length={len(k)}  " + ("⚠️ " + "; ".join(issues) if issues else "format looks OK"))

print("Where the key comes from:")
env_key = os.environ.get("GROQ_API_KEY")
inspect("Codespaces secret / terminal env", env_key)

dot_key = None
if os.path.exists(".env"):
    for line in open(".env"):
        if line.startswith("GROQ_API_KEY="):
            dot_key = line.rstrip("\n").split("=", 1)[1]
inspect(".env file", dot_key)

if env_key and dot_key and env_key.strip() != dot_key.strip():
    print("   ⚠️  The two values DIFFER. The terminal env wins; delete the .env line if it's stale.")

key = (env_key or dot_key or "").strip().strip("\"'")
if not key:
    raise SystemExit("\n❌ No key found anywhere. Add the Codespaces secret GROQ_API_KEY and restart.")

print("\nAsking Groq (list models, uses no quota)…")
req = urllib.request.Request("https://api.groq.com/openai/v1/models",
                             headers={"Authorization": f"Bearer {key}", "User-Agent": "Chronoscope/0.1"})
try:
    with urllib.request.urlopen(req, timeout=20) as r:
        ids = [m["id"] for m in json.load(r)["data"]]
    print(f"✅ Key works ({mask(key)}). {len(ids)} models, e.g. {', '.join(sorted(ids)[:4])}")
    if key != (env_key or dot_key):
        print("   Note: it only worked after removing spaces/quotes. Fix the stored value.")
except urllib.error.HTTPError as e:
    print(f"❌ HTTP {e.code}: Groq rejects this key. Create a new one at console.groq.com/keys "
          f"and paste it carefully (no quotes, no spaces).")
