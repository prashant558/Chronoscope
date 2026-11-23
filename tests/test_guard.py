"""Unit test for the headline guard (no network, no LLM)."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from agent.agent import verify_headlines

known = ["JOYOUS EAST GERMANS POUR THROUGH WALL; PARTY PLEDGES FREEDOMS, AND CITY EXULTS",
         "EAST GERMANY OPENS FRONTIER TO THE WEST FOR MIGRATION OR TRAVEL; THOUSANDS CROSS"]
answer = """### What happened
Something "quoted but not a headline section" happened.
### In the newspapers
- 📰 **“JOYOUS EAST GERMANS POUR THROUGH WALL; PARTY PLEDGES FREEDOMS, AND CITY EXULTS”**
- “U.S. Senate Confirms Bush Cabinet Picks”
- “East Germany Opens Frontier to the West for Migration or Travel; Thousands Cross”
### The sky that night
Dark."""
out, removed = verify_headlines(answer, known)
assert len(removed) == 1 and "Senate" in removed[0], removed
assert "JOYOUS" in out and "Frontier" in out, "real headlines must survive (case-insensitive)"
assert "quoted but not" in out, "quotes outside the newspaper section must be untouched"
print("✅ Guard keeps real headlines, removes invented ones, ignores other sections")

from agent.agent import attach_sources
src = [{"ref": 1, "article": "Vostok 1", "section": "Flight", "url": "https://en.wikipedia.org/wiki/Vostok_1", "text": "a"},
       {"ref": 2, "article": "Vostok 1", "section": "Introduction", "url": "https://en.wikipedia.org/wiki/Vostok_1", "text": "b"}]
out = attach_sources("Launched [ref 2]. Orbited [ref: 1, 2]. Fake [9].\n### Sources\n[9] made up", src)
assert "[2]" in out and "[1][2]" in out and "[9]" not in out and "made up" not in out, out
assert "#Flight" in out and "Vostok_1\n" in out + "\n", out
print("✅ Citations normalised, fake refs dropped, Sources built from real passages")
