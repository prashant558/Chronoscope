"""Chronoscope web UI."""
import asyncio, json, sys
from datetime import date
from pathlib import Path
import streamlit as st

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from agent.agent import Agent

st.set_page_config(page_title="Chronoscope", page_icon="🔭", layout="centered")
st.title("🔭 Chronoscope")
st.caption("Pick any date. An AI agent checks history, real newspaper front pages and the night sky, "
           "then writes a time capsule with sources.")

EXAMPLES = {"🧱 Berlin Wall": "9 November 1989", "🌕 Apollo 11": "20 July 1969",
            "🚀 Gagarin": "12 April 1961", "🇮🇳 Chandrayaan-3": "the day Chandrayaan-3 landed on the Moon"}
ICONS = {"sky": "🌌", "history": "📜", "news": "📰", "knowledge": "📚"}

ss = st.session_state
ss.setdefault("cache", {})

for col, (label, q) in zip(st.columns(len(EXAMPLES)), EXAMPLES.items()):
    if col.button(label):
        ss.question, ss.go = q, True

with st.form("ask"):
    c1, c2 = st.columns(2)
    d = c1.date_input("Date", value=date(1989, 11, 9), min_value=date(1851, 9, 18),
                      max_value=date.today(), format="DD.MM.YYYY")
    place = c2.text_input("Place (optional)", placeholder="e.g. Tokyo")
    free = st.text_input("…or ask in words (optional)", placeholder="the first day of the 21st century in Tokyo")
    if st.form_submit_button("Open time capsule ✨", type="primary"):
        ss.question = free.strip() or (d.isoformat() + (f" in {place.strip()}" if place.strip() else ""))
        ss.go = True


async def run_agent(question, status):
    def on_event(e):
        if e["type"] == "thinking":
            status.update(label=f"Step {e['step']}: deciding what to look up…")
        elif e["type"] == "tool":
            args = ", ".join(f"{k}={v}" for k, v in e["args"].items())
            note = "reused" if e["cached"] else f"{e['seconds']}s"
            flag = " ⚠️" if e["error"] else ""
            status.write(f"{ICONS.get(e['server'], '🔧')} **{e['tool']}**({args}) · {note}{flag}")
    async with Agent() as agent:
        return await agent.run(question, verbose=False, on_event=on_event)


if ss.get("go"):
    ss.go = False
    q = ss.question
    if q in ss.cache:
        ss.last = ss.cache[q]
    else:
        with st.status(f"Researching “{q}”…", expanded=True) as status:
            try:
                out = asyncio.run(run_agent(q, status))
                status.update(label=f"Done in {out['seconds']}s", state="complete", expanded=False)
                ss.cache[q] = ss.last = out
            except Exception as e:
                status.update(label="Something went wrong", state="error")
                st.error(f"{type(e).__name__}: {e}")
                st.stop()

out = ss.get("last")
if out:
    st.markdown(out["answer"])
    st.divider()
    m1, m2, m3 = st.columns(3)
    m1.metric("Tool calls", len(out["trace"]))
    m2.metric("Time", f"{out['seconds']}s")
    m3.metric("Invented headlines blocked", len(out["removed_headlines"]))
    st.caption(f"Written by {out['model']} · data: Wikipedia, The New York Times Archive, NASA JPL ephemeris")
    with st.expander("🔍 How the agent got here"):
        st.dataframe([{"step": t["step"], "server": f"{ICONS.get(t['server'], '')} {t['server']}",
                       "tool": t["tool"], "arguments": json.dumps(t["args"], ensure_ascii=False),
                       "seconds": t["seconds"], "reused": t["cached"], "error": t["error"]}
                      for t in out["trace"]], hide_index=True)
        if out["removed_headlines"]:
            st.warning("The headline guard removed:\n\n" + "\n\n".join(out["removed_headlines"]))
