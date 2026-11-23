"""Starts sky_mcp as a real MCP server and calls it as a client would."""
import asyncio, json, sys
from pathlib import Path
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

SERVER = Path(__file__).resolve().parent.parent / "servers" / "sky_mcp.py"

async def call(session, tool, args):
    res = await session.call_tool(tool, args)
    return json.loads(res.content[0].text)

async def main():
    params = StdioServerParameters(command=sys.executable, args=[str(SERVER)])
    async with stdio_client(params) as (r, w):
        async with ClientSession(r, w) as s:
            await s.initialize()
            tools = [t.name for t in (await s.list_tools()).tools]
            assert {"sky_on_date", "list_cities"} <= set(tools), tools
            print("✅ Tools exposed:", tools)

            cases = [
                ("Berlin Wall falls", {"date": "1989-11-09", "time": "23:00", "city": "berlin"}),
                ("Apollo 11 landing", {"date": "1969-07-20", "time": "16:17", "city": "houston"}),
                ("Tokyo via coords", {"date": "2000-01-01", "time": "00:00",
                                      "lat": 35.676, "lon": 139.65, "timezone": "Asia/Tokyo"}),
            ]
            for label, args in cases:
                out = await call(s, "sky_on_date", args)
                assert "error" not in out, out
                ups = ", ".join(f"{b['body']} ({b['direction']})" for b in out["above_horizon"]) or "none"
                print(f"✅ {label}: {out['sky']}, {out['moon']['phase']} "
                      f"{out['moon']['illuminated_pct']}%, up: {ups}")

            bad = await call(s, "sky_on_date", {"date": "1850-01-01"})
            assert "error" in bad
            bad = await call(s, "sky_on_date", {"date": "2000-01-01", "city": "atlantis"})
            assert "error" in bad
            print("✅ Bad inputs rejected cleanly")
    print("\n🚀 sky-mcp works as a real MCP server")

asyncio.run(main())
