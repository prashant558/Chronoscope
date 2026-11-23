"""history-mcp: what happened on a date, via Wikipedia's free On This Day feed."""
import json, sys, urllib.parse, urllib.request, urllib.error
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))   # for cache.py
import cache
from mcp.server.mcpserver import MCPServer

mcp = MCPServer("history-mcp")

UA = "Chronoscope/0.1 (https://github.com/prashant558/Chronoscope; portfolio project)"
BASE = "https://en.wikipedia.org/api/rest_v1"

def _get(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)

def _slim(item):
    page = (item.get("pages") or [{}])[0]
    return {
        "year": item.get("year"),
        "text": item.get("text", "").strip(),
        "article": page.get("titles", {}).get("normalized") or page.get("title"),
        "url": page.get("content_urls", {}).get("desktop", {}).get("page"),
    }

def _on_this_day(month, day):
    key = f"otd:{month:02d}-{day:02d}"
    data = cache.get(key, max_age_s=30 * 86400)
    if data is None:
        data = _get(f"{BASE}/feed/onthisday/all/{month:02d}/{day:02d}")
        cache.put(key, data)
    return data

@mcp.tool()
def events_on_date(date: str, other_years: int = 5) -> dict:
    """What happened on a date. date: YYYY-MM-DD.

    Returns events from that exact year first, then notable events on the same
    calendar day in other years (closest years first), plus births and deaths.
    """
    try:
        d = datetime.strptime(date, "%Y-%m-%d")
    except ValueError:
        return {"error": "Use date format YYYY-MM-DD"}
    try:
        data = _on_this_day(d.month, d.day)
    except urllib.error.HTTPError as e:
        return {"error": f"Wikipedia returned HTTP {e.code}"}
    except Exception as e:
        return {"error": f"Could not reach Wikipedia: {e}"}

    events = [_slim(x) for x in (data.get("events", []) + data.get("selected", []))]
    seen, uniq = set(), []
    for e in events:                       # 'selected' overlaps 'events'
        k = (e["year"], e["text"][:60])
        if k not in seen:
            seen.add(k); uniq.append(e)

    same_year = [e for e in uniq if e["year"] == d.year]
    others = sorted((e for e in uniq if e["year"] != d.year),
                    key=lambda e: abs((e["year"] or 0) - d.year))[:other_years]
    births = [_slim(x) for x in data.get("births", []) if x.get("year") == d.year][:5]
    deaths = [_slim(x) for x in data.get("deaths", []) if x.get("year") == d.year][:5]

    return {
        "date": date,
        "same_year_events": same_year,
        "same_day_other_years": others,
        "births_that_year": births,
        "deaths_that_year": deaths,
        "source": "Wikipedia On This Day",
    }

@mcp.tool()
def article_summary(title: str) -> dict:
    """Short Wikipedia summary of a topic, e.g. 'Fall of the Berlin Wall'."""
    key = f"sum:{title.lower()}"
    if (hit := cache.get(key)) is not None:
        return hit
    try:
        data = _get(f"{BASE}/page/summary/{urllib.parse.quote(title.replace(' ', '_'))}")
    except urllib.error.HTTPError as e:
        return {"error": f"No Wikipedia article found for '{title}'" if e.code == 404
                else f"Wikipedia returned HTTP {e.code}"}
    except Exception as e:
        return {"error": f"Could not reach Wikipedia: {e}"}
    out = {
        "title": data.get("title"),
        "description": data.get("description"),
        "summary": data.get("extract"),
        "url": data.get("content_urls", {}).get("desktop", {}).get("page"),
    }
    cache.put(key, out)
    return out

if __name__ == "__main__":
    mcp.run(transport="stdio")
