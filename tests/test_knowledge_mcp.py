"""RAG server: retrieves the right passage from a full article, over real MCP."""
import asyncio, json, sys, time
from pathlib import Path
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client, get_default_environment

SERVER = Path(__file__).resolve().parent.parent / "servers" / "knowledge_mcp.py"

async def call(s, args):
    res = await s.call_tool("research", args)
    return json.loads("".join(getattr(c, "text", "") for c in res.content))

async def main():
    params = StdioServerParameters(command=sys.executable, args=[str(SERVER)], env=get_default_environment())
    async with stdio_client(params) as (r, w):
        async with ClientSession(r, w) as s:
            await s.initialize()
            print("✅ Tools:", [t.name for t in (await s.list_tools()).tools])

            t = time.time()   # first call downloads the model (~70 MB once) and indexes the article
            out = await call(s, {"topic": "Vostok 1", "question": "How did Gagarin land at the end of the flight?"})
            assert "error" not in out, out
            text = " ".join(p["text"].lower() for p in out["passages"])
            assert any(w in text for w in ("parachute", "eject")), [p["section"] for p in out["passages"]]
            print(f"✅ Retrieved landing passage ({time.time()-t:.1f}s, backend={out['backend']}, "
                  f"indexed_now={out['indexed_now']}), sections: {[p['section'] for p in out['passages']]}")

            t = time.time()
            out = await call(s, {"topic": "Vostok 1", "question": "Why was the flight important?"})
            assert out["indexed_now"] is False
            print(f"✅ Second question reuses the index: {time.time()-t:.1f}s")

            assert "error" in await call(s, {"topic": "Zxqvbnm Nonexistent", "question": "x"})
            print("✅ Missing article handled")
    print("\n🚀 knowledge-mcp (RAG) works")

asyncio.run(main())
