"""Record docs/demo.gif: start the app, click an example, capture the agent working."""
import subprocess, sys, time, glob, os, urllib.request
from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
os.chdir(ROOT)
app = subprocess.Popen([sys.executable, "-m", "streamlit", "run", "app.py", "--server.port", "8599",
                        "--server.headless", "true"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
try:
    for _ in range(60):                                    # pre-flight: wait for the app
        try: urllib.request.urlopen("http://localhost:8599", timeout=1); break
        except Exception: time.sleep(1)
    else: sys.exit("❌ App did not start")
    vid = ROOT / "data" / "video"; vid.mkdir(parents=True, exist_ok=True)
    for f in vid.glob("*.webm"): f.unlink()
    with sync_playwright() as p:
        b = p.chromium.launch()
        ctx = b.new_context(viewport={"width": 1000, "height": 900},
                            record_video_dir=str(vid), record_video_size={"width": 1000, "height": 900})
        page = ctx.new_page()
        page.goto("http://localhost:8599"); page.wait_for_selector("text=Chronoscope"); time.sleep(2)
        page.get_by_role("button", name="🧱 Berlin Wall").click()
        page.wait_for_selector("text=What happened", timeout=180_000); time.sleep(2)
        for _ in range(8): page.mouse.wheel(0, 250); time.sleep(0.6)   # scroll through the capsule
        time.sleep(1.5); ctx.close(); b.close()
    webm = sorted(vid.glob("*.webm"))[-1]
    (ROOT / "docs").mkdir(exist_ok=True)
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(webm), "-vf",
                    "fps=8,scale=800:-1:flags=lanczos,split[a][b];[a]palettegen=max_colors=128[p];[b][p]paletteuse",
                    "docs/demo.gif"], check=True)
    mb = (ROOT / "docs" / "demo.gif").stat().st_size / 1e6
    print(f"✅ docs/demo.gif written ({mb:.1f} MB)" + ("  ⚠️ >10 MB, consider fps=6" if mb > 10 else ""))
finally:
    app.terminate()
