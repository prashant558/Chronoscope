"""knowledge-mcp: RAG over Wikipedia. Full article → chunks → local embeddings → top passages."""
import json, os, re, sys, urllib.parse, urllib.request, urllib.error
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("ANONYMIZED_TELEMETRY", "False")
from mcp.server.mcpserver import MCPServer

mcp = MCPServer("knowledge-mcp")
DATA = ROOT / "data"
UA = "Chronoscope/0.1 (https://github.com/prashant558/Chronoscope; portfolio project)"
MAX_ARTICLE_CHARS = 60000
CHUNK_CHARS = 900
SKIP_SECTIONS = {"references", "external links", "see also", "notes", "further reading",
                 "bibliography", "sources", "citations", "footnotes"}

# ---------- embeddings (local, lazy-loaded) ----------
_embedder = None
def _embed(texts, query=False):
    global _embedder
    if _embedder is None:
        from fastembed import TextEmbedding
        _embedder = TextEmbedding("BAAI/bge-small-en-v1.5", cache_dir=str(DATA / "models"))
    fn = _embedder.query_embed if query else _embedder.passage_embed
    return [[float(x) for x in v] for v in fn(texts)]

# ---------- vector store: ChromaDB, numpy fallback ----------
try:
    import chromadb
    _col = chromadb.PersistentClient(path=str(DATA / "chroma")).get_or_create_collection(
        "wikipedia", metadata={"hnsw:space": "cosine"})
    BACKEND = "chromadb"
except Exception:
    _col, BACKEND = None, "numpy"
    (DATA / "vectors").mkdir(parents=True, exist_ok=True)

def _slug(t): return re.sub(r"[^a-z0-9]+", "_", t.lower()).strip("_")

def _is_indexed(title):
    if _col is not None:
        return bool(_col.get(where={"article": title}, limit=1)["ids"])
    return (DATA / "vectors" / f"{_slug(title)}.json").exists()

def _store(title, url, chunks):
    vecs = _embed([c["text"] for c in chunks])
    if _col is not None:
        _col.add(ids=[f"{title}::{i}" for i in range(len(chunks))], embeddings=vecs,
                 documents=[c["text"] for c in chunks],
                 metadatas=[{"article": title, "section": c["section"], "url": url} for c in chunks])
    else:
        json.dump({"url": url, "chunks": chunks, "vecs": vecs},
                  open(DATA / "vectors" / f"{_slug(title)}.json", "w"))

def _search(title, question, k):
    q = _embed([question], query=True)[0]
    if _col is not None:
        r = _col.query(query_embeddings=[q], n_results=k, where={"article": title})
        return [{"section": m["section"], "text": d} for d, m in zip(r["documents"][0], r["metadatas"][0])]
    import numpy as np
    d = json.load(open(DATA / "vectors" / f"{_slug(title)}.json"))
    V, qv = np.array(d["vecs"]), np.array(q)
    sims = V @ qv / (np.linalg.norm(V, axis=1) * np.linalg.norm(qv) + 1e-9)
    return [d["chunks"][i] for i in np.argsort(-sims)[:k]]

# ---------- Wikipedia ----------
def _fetch(topic):
    qs = urllib.parse.urlencode({"action": "query", "prop": "extracts", "explaintext": 1,
                                 "redirects": 1, "titles": topic, "format": "json"})
    req = urllib.request.Request(f"https://en.wikipedia.org/w/api.php?{qs}", headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as r:
        page = next(iter(json.load(r)["query"]["pages"].values()))
    if "missing" in page or not page.get("extract"):
        return None
    title = page["title"]
    return title, f"https://en.wikipedia.org/wiki/{urllib.parse.quote(title.replace(' ', '_'))}", \
           page["extract"][:MAX_ARTICLE_CHARS]

def _chunk(text):
    chunks, section, buf = [], "Introduction", ""
    for line in text.split("\n"):
        line = line.strip()
        h = re.match(r"^=+\s*(.+?)\s*=+$", line)
        if h:
            if buf: chunks.append({"section": section, "text": buf.strip()}); buf = ""
            section = h.group(1); continue
        if not line or section.lower() in SKIP_SECTIONS:
            continue
        if len(buf) + len(line) > CHUNK_CHARS and buf:
            chunks.append({"section": section, "text": buf.strip()}); buf = ""
        buf += line + " "
    if buf: chunks.append({"section": section, "text": buf.strip()})
    return [c for c in chunks if len(c["text"]) > 80]

# ---------- tool ----------
@mcp.tool()
def research(topic: str, question: str, k: int = 3) -> dict:
    """Retrieve the most relevant passages from the FULL Wikipedia article on a topic.

    topic: article title, e.g. 'Vostok 1' or 'Fall of the Berlin Wall'.
    question: what you want to know, e.g. 'What happened and why did it matter?'
    Returns passages with their section names. Use these as the factual basis for the answer.
    """
    k = max(1, min(int(k), 5))
    try:
        got = _fetch(topic)
    except Exception as e:
        return {"error": f"Could not reach Wikipedia: {e}"}
    if not got:
        return {"error": f"No Wikipedia article found for '{topic}'"}
    title, url, text = got
    newly = False
    if not _is_indexed(title):
        chunks = _chunk(text)
        if not chunks:
            return {"error": f"Article '{title}' has no usable text"}
        _store(title, url, chunks); newly = True
    return {"article": title, "url": url, "passages": _search(title, question, k),
            "indexed_now": newly, "backend": BACKEND}

if __name__ == "__main__":
    mcp.run(transport="stdio")
