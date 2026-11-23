"""Starts history_mcp as a real MCP server and calls it as a client would."""
import asyncio, json, sys, time
from pathlib import Path
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

SERVER = Path(__file__).resolve().parent.parent / "servers" / "history_mcp.py"

async def call(s, tool, args):
    res = await s.call_tool(tool, args)
    return json.loads(res.content[0].text)

async def main():
    params = StdioServerParameters(command=sys.executable, args=[str(SERVER)])
    async with stdio_client(params) as (r, w):
        async with ClientSession(r, w) as s:
            await s.initialize()
            tools = {t.name for t in (await s.list_tools()).tools}
            assert {"events_on_date", "article_summary"} <= tools, tools
            print("✅ Tools exposed:", sorted(tools))

            for label, date, must in [("Berlin Wall", "1989-11-09", "berlin"),
                                      ("Apollo 11", "1969-07-20", "apollo")]:
                t = time.time()
                out = await call(s, "events_on_date", {"date": date})
                assert "error" not in out, out
                texts = " ".join(e["text"].lower() for e in out["same_year_events"])
                assert must in texts, f"'{must}' not found in same-year events for {date}"
                first = out["same_year_events"][0]["text"][:90]
                print(f"✅ {label} ({time.time()-t:.1f}s): {len(out['same_year_events'])} same-year "
                      f"event(s), e.g. \"{first}…\"")

            t = time.time()
            await call(s, "events_on_date", {"date": "1989-11-09"})
            print(f"✅ Cache hit on repeat: {time.time()-t:.2f}s")

            summ = await call(s, "article_summary", {"title": "Fall of the Berlin Wall"})
            assert summ.get("summary"), summ
            print(f"✅ Summary: {summ['summary'][:90]}…")

            assert "error" in await call(s, "events_on_date", {"date": "9-11-1989"})
            assert "error" in await call(s, "article_summary", {"title": "Zxqvbnm Nonexistent Topic"})
            print("✅ Bad inputs rejected cleanly")
    print("\n🚀 history-mcp works as a real MCP server")

asyncio.run(main())
