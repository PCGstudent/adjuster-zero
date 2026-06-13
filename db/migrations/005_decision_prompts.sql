-- 005_decision_prompts.sql
-- Persist the exact prompt we send to the LLM on each decision, so the
-- step-by-step walkthrough can show the request verbatim (thesis 9: a decision is
-- first-class provenance — model, tokens, latency, citations AND the prompt — not a
-- log line). The pre-existing prompt_hash column kept only a fingerprint; these hold
-- the full text. NULL for pure-rule decisions (e.g. the deterministic router), which
-- never call an LLM.

ALTER TABLE agent_decisions ADD COLUMN IF NOT EXISTS prompt TEXT;
ALTER TABLE agent_decisions ADD COLUMN IF NOT EXISTS system_prompt TEXT;
