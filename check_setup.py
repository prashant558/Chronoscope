"""Chronoscope setup check: Gemini, NYT, Skyfield."""
import os, sys, json, importlib.util, urllib.request, urllib.error

results = {}

def mask(k):
    return f"{k[:4]}…{k[-4:]}" if k and len(k) > 8 else "(too short?)"

def header(t):
    print(f"\n── {t} " + "─" * (40 - len(t)))

# ---------- Pre-flight: packages ----------
header("Packages")
need = {"google.genai": "google-genai", "skyfield": "skyfield"}
missing = [pkg for mod, pkg in need.items()
           if importlib.util.find_spec(mod.split(".")[0]) is None
           or (mod == "google.genai" and importlib.util.find_spec("google.genai") is None)]
if missing:
    sys.exit(f"❌ Missing packages. Run:  pip install {' '.join(missing)}")
print("✅ google-genai and skyfield installed")

# ---------- 1. Gemini ----------
header("Gemini API")
gkey = os.environ.get("GEMINI_API_KEY")
if not gkey:
    print("❌ GEMINI_API_KEY not set (add Codespaces secret, then restart codespace)")
    results["Gemini"] = False
else:
    print(f"Key found: {mask(gkey)}")
    try:
        import llm
        model, text = llm.generate("Reply with exactly: OK", verbose=True)
        print(f"✅ {model} replied: {text.strip()}")
        results["Gemini"] = True
    except Exception as e:
        print(f"❌ Gemini failed: {str(e)[:200]}")
        results["Gemini"] = False

# ---------- 2. NYT ----------
header("NYT Archive API")
nkey = os.environ.get("NYT_API_KEY")
if not nkey:
    print("❌ NYT_API_KEY not set (add Codespaces secret, then restart codespace)")
    results["NYT"] = False
else:
    print(f"Key found: {mask(nkey)}  (fetching Nov 1989, can take ~30 s)")
    url = f"https://api.nytimes.com/svc/archive/v1/1989/11.json?api-key={nkey}"
    try:
        with urllib.request.urlopen(url, timeout=90) as r:
            docs = json.load(r)["response"]["docs"]
        hits = [d["headline"]["main"] for d in docs
                if "berlin" in (d.get("headline", {}).get("main") or "").lower()]
        print(f"✅ {len(docs)} articles; sample: {hits[0] if hits else '(no Berlin headline)'}")
        results["NYT"] = True
    except urllib.error.HTTPError as e:
        hint = {401: "key invalid or Archive API not enabled on your NYT app",
                429: "rate limit (5/min, 500/day), wait and retry"}.get(e.code, e.reason)
        print(f"❌ HTTP {e.code}: {hint}")
        results["NYT"] = False
    except Exception as e:
        print(f"❌ NYT failed: {e}")
        results["NYT"] = False

# ---------- 3. Skyfield (no key) ----------
header("Skyfield (no key needed)")
try:
    from skyfield.api import load, wgs84
    from skyfield import almanac
    os.makedirs("data", exist_ok=True)
    loader = load.__class__("data")          # store ephemeris in ./data
    eph = loader("de421.bsp")                 # one-time ~17 MB download
    ts = loader.timescale()
    t = ts.utc(1989, 11, 9, 22)               # Berlin Wall night, 23:00 local
    phase = almanac.moon_phase(eph, t).degrees
    berlin = eph["earth"] + wgs84.latlon(52.52, 13.405)
    up = []
    for name, key in [("Moon", "moon"), ("Mars", "mars"), ("Jupiter", "jupiter barycenter"),
                      ("Saturn", "saturn barycenter"), ("Venus", "venus")]:
        alt, _, _ = berlin.at(t).observe(eph[key]).apparent().altaz()
        if alt.degrees > 0:
            up.append(name)
    print(f"✅ 9 Nov 1989, Berlin: moon phase {phase:.0f}°, above horizon: {', '.join(up) or 'none'}")
    results["Skyfield"] = True
except Exception as e:
    print(f"❌ Skyfield failed: {e}")
    results["Skyfield"] = False

# ---------- Summary ----------
header("Summary")
for k, ok in results.items():
    print(f"{'✅' if ok else '❌'} {k}")
if not all(results.values()):
    sys.exit(1)
print("\n🚀 All good, ready to build the MCP servers!")
