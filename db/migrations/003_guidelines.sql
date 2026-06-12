-- ╔══════════════════════════════════════════════════════════════════════════╗
-- ║ 003_guidelines.sql — pgvector store for the guideline corpus (RAG).         ║
-- ║ Populated by `make ingest` (chunk → embed → upsert). 768-dim to match the   ║
-- ║ embedder (gemini-embedding-001 @ output_dimensionality=768 / local-hash).   ║
-- ╚══════════════════════════════════════════════════════════════════════════╝

CREATE TABLE IF NOT EXISTS guideline_chunks (
  id        TEXT PRIMARY KEY,
  doc       TEXT NOT NULL,
  section   TEXT,
  text      TEXT NOT NULL,
  embedding vector(768)
);

-- Full-text index for the keyword half of hybrid retrieval.
CREATE INDEX IF NOT EXISTS guideline_chunks_fts
  ON guideline_chunks USING gin (to_tsvector('english', text));

-- The corpus is tiny (~30 chunks); a cosine seq-scan is fine. An ivfflat index
-- can be added later once the corpus grows:
--   CREATE INDEX guideline_chunks_vec ON guideline_chunks
--     USING ivfflat (embedding vector_cosine_ops) WITH (lists = 10);

-- RLS: public read (viewer mode); service-role writer bypasses RLS.
ALTER TABLE guideline_chunks ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS guideline_chunks_read ON guideline_chunks;
CREATE POLICY guideline_chunks_read ON guideline_chunks
  FOR SELECT TO anon, authenticated USING (true);
