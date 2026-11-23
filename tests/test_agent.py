"""End-to-end: the agent must use all three servers and produce a capsule."""
import asyncio, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from agent.agent import Agent

async def main():
    async with Agent() as a:
        assert {"sky_on_date", "events_on_date", "headlines_on_date"} <= set(a.route), a.route
        print("✅ All tools discovered over MCP")
        out = await a.run("20 July 1969", verbose=False)
    used = {t["tool"] for t in out["trace"]}
    servers = {t["server"] for t in out["trace"]}
    print(f"   tools used: {sorted(used)}")
    assert {"sky", "history", "news", "knowledge"} <= servers, f"Not all servers used: {servers}"
    print("✅ Agent used all three servers")
    ans = out["answer"].lower()
    assert "###" in out["answer"] and len(out["answer"]) > 300, "Capsule too short / wrong format"
    assert any(k in ans for k in ("moon", "apollo")), "Capsule doesn't mention the Moon landing"
    print(f"✅ Capsule written ({len(out['answer'])} chars) by {out['model']} in {out['seconds']}s")
    print("\n🚀 Agent works end to end")

asyncio.run(main())
