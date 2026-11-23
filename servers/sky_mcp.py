"""sky-mcp: what the night sky looked like at a place and time."""
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from mcp.server.mcpserver import MCPServer
from skyfield.api import Loader, wgs84
from skyfield import almanac

mcp = MCPServer("sky-mcp")

DATA = Path(__file__).resolve().parent.parent / "data"
DATA.mkdir(exist_ok=True)
_load = Loader(str(DATA), verbose=False)      # verbose=False: never print to stdout (breaks MCP stdio)
eph = _load("de421.bsp")                      # covers 1900–2050
ts = _load.timescale()

CITIES = {  # name: (lat, lon, timezone)
    "berlin": (52.52, 13.405, "Europe/Berlin"),
    "braunschweig": (52.27, 10.52, "Europe/Berlin"),
    "london": (51.507, -0.128, "Europe/London"),
    "paris": (48.857, 2.352, "Europe/Paris"),
    "new york": (40.713, -74.006, "America/New_York"),
    "washington": (38.907, -77.037, "America/New_York"),
    "houston": (29.760, -95.370, "America/Chicago"),
    "los angeles": (34.052, -118.244, "America/Los_Angeles"),
    "tokyo": (35.676, 139.650, "Asia/Tokyo"),
    "delhi": (28.614, 77.209, "Asia/Kolkata"),
    "mumbai": (19.076, 72.878, "Asia/Kolkata"),
    "ahmedabad": (23.023, 72.571, "Asia/Kolkata"),
    "moscow": (55.756, 37.617, "Europe/Moscow"),
    "beijing": (39.904, 116.407, "Asia/Shanghai"),
    "sydney": (-33.869, 151.209, "Australia/Sydney"),
    "cape canaveral": (28.392, -80.608, "America/New_York"),
}

BODIES = [("Moon", "moon"), ("Mercury", "mercury"), ("Venus", "venus"),
          ("Mars", "mars"), ("Jupiter", "jupiter barycenter"), ("Saturn", "saturn barycenter")]

def _phase_name(deg):
    names = ["New Moon", "Waxing Crescent", "First Quarter", "Waxing Gibbous",
             "Full Moon", "Waning Gibbous", "Last Quarter", "Waning Crescent"]
    return names[int(((deg + 22.5) % 360) // 45)]

def _compass(az):
    return ["N", "NE", "E", "SE", "S", "SW", "W", "NW"][int(((az + 22.5) % 360) // 45)]

def _sky_state(sun_alt):
    if sun_alt > 0: return "daylight"
    if sun_alt > -6: return "civil twilight"
    if sun_alt > -12: return "nautical twilight"
    if sun_alt > -18: return "astronomical twilight"
    return "fully dark"

@mcp.tool()
def list_cities() -> list[str]:
    """List the city names sky_on_date accepts without coordinates."""
    return sorted(CITIES)

@mcp.tool()
def sky_on_date(date: str, time: str = "22:00", city: str = "berlin",
                lat: float | None = None, lon: float | None = None,
                timezone: str = "UTC") -> dict:
    """Describe the sky at a place and local time.

    date: YYYY-MM-DD (1900-2050). time: HH:MM local time.
    Use a known city name, or pass lat, lon and an IANA timezone (e.g. 'Asia/Tokyo').
    Returns moon phase, illumination, darkness level, and visible planets with direction.
    """
    try:
        local = datetime.strptime(f"{date} {time}", "%Y-%m-%d %H:%M")
    except ValueError:
        return {"error": "Use date YYYY-MM-DD and time HH:MM"}
    if not 1900 <= local.year <= 2050:
        return {"error": "Date must be between 1900 and 2050"}

    if lat is not None and lon is not None:
        place, tz = f"{lat:.3f}, {lon:.3f}", timezone
    else:
        key = city.lower().strip()
        if key not in CITIES:
            return {"error": f"Unknown city '{city}'. Pass lat/lon/timezone or use: {', '.join(sorted(CITIES))}"}
        lat, lon, tz = CITIES[key]
        place = city.title()

    try:
        aware = local.replace(tzinfo=ZoneInfo(tz))
    except Exception:
        return {"error": f"Unknown timezone '{tz}'"}
    t = ts.from_datetime(aware)
    observer = eph["earth"] + wgs84.latlon(lat, lon)

    sun_alt = observer.at(t).observe(eph["sun"]).apparent().altaz()[0].degrees
    phase_deg = almanac.moon_phase(eph, t).degrees
    illum = almanac.fraction_illuminated(eph, "moon", t)

    visible, below = [], []
    for name, key in BODIES:
        alt, az, _ = observer.at(t).observe(eph[key]).apparent().altaz()
        if alt.degrees > 0:
            visible.append({"body": name, "altitude_deg": round(alt.degrees, 1),
                            "direction": _compass(az.degrees)})
        else:
            below.append(name)

    return {
        "place": place, "local_time": aware.strftime("%Y-%m-%d %H:%M %Z"),
        "sky": _sky_state(sun_alt),
        "moon": {"phase": _phase_name(phase_deg), "illuminated_pct": round(illum * 100)},
        "above_horizon": sorted(visible, key=lambda b: -b["altitude_deg"]),
        "below_horizon": below,
    }

if __name__ == "__main__":
    mcp.run(transport="stdio")
