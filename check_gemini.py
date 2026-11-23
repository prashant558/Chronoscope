"""Find the newest working Gemini Flash model for this key."""
import os, re, sys
from google import genai

key = os.environ.get("GEMINI_API_KEY")
if not key:
    sys.exit("❌ GEMINI_API_KEY not set")

client = genai.Client(api_key=key)

def version(name):
    m = re.search(r"gemini-(\d+(?:\.\d+)?)", name)
    return float(m.group(1)) if m else 0.0

models = [m.name.replace("models/", "") for m in client.models.list()
          if "flash" in m.name
          and "generateContent" in (m.supported_actions or [])
          and not any(x in m.name for x in ("image", "tts", "live", "audio", "lite"))]

# Newest first, stable before preview
models.sort(key=lambda n: (version(n), "preview" not in n and "exp" not in n), reverse=True)
print("Candidates:", ", ".join(models[:5]) or "none")

for model in models:
    try:
        r = client.models.generate_content(model=model, contents="Reply with exactly: OK")
        print(f"✅ {model} replied: {r.text.strip()}")
        with open(".env", "a") as f:
            f.write(f"GEMINI_MODEL={model}\n")
        print(f"   Saved GEMINI_MODEL={model} to .env")
        break
    except Exception as e:
        code = "404 retired" if "404" in str(e) else "429 quota" if "429" in str(e) else str(e)[:80]
        print(f"   skip {model}: {code}")
else:
    sys.exit("❌ No working Flash model found")
