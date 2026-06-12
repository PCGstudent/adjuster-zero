"""Section-aware chunking of the guideline corpus (db/guidelines/*.md).

doc_id = the H1 (e.g. 'G-AUTO-GLASS'); each H2 section becomes one chunk with a
stable id `{doc_id}#c{n}`.
"""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel

# repo_root/db/guidelines  (chunk.py is agent/src/adjuster_zero/rag/chunk.py)
GUIDELINES_DIR = Path(__file__).resolve().parents[4] / "db" / "guidelines"


class GuidelineChunk(BaseModel):
    id: str
    doc: str
    section: str
    text: str


def _chunk_markdown(md: str) -> tuple[str, list[tuple[str, str]]]:
    """Return (doc_id, [(section_title, section_text), ...])."""
    lines = md.splitlines()
    doc_id = "UNKNOWN"
    sections: list[tuple[str, list[str]]] = []
    for line in lines:
        if line.startswith("# ") and doc_id == "UNKNOWN":
            doc_id = line[2:].split("—")[0].strip()
        elif line.startswith("## "):
            sections.append((line[3:].strip(), []))
        elif sections:
            sections[-1][1].append(line)
    return doc_id, [(title, "\n".join(body).strip()) for title, body in sections]


def load_chunks(directory: Path | None = None) -> list[GuidelineChunk]:
    d = directory or GUIDELINES_DIR
    chunks: list[GuidelineChunk] = []
    if not d.exists():
        return chunks
    for path in sorted(d.glob("*.md")):
        doc_id, sections = _chunk_markdown(path.read_text(encoding="utf-8"))
        for n, (title, body) in enumerate(sections):
            chunks.append(GuidelineChunk(
                id=f"{doc_id}#c{n}", doc=doc_id, section=title,
                text=f"{title}. {body}",
            ))
    return chunks
