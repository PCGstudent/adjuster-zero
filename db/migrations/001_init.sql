-- ╔══════════════════════════════════════════════════════════════════════════╗
-- ║ Adjuster Zero — 001_init.sql                                               ║
-- ║ Relational schema (blueprint Part 6) + config + documents + llm_usage,     ║
-- ║ pgvector + pg_cron extensions, and RLS (operator read/write, viewer RO).   ║
-- ║ Apply via the Supabase SQL editor (see db/README.md). Idempotent-ish:      ║
-- ║ uses IF NOT EXISTS / CREATE OR REPLACE where practical.                    ║
-- ╚══════════════════════════════════════════════════════════════════════════╝

-- ── Extensions ──────────────────────────────────────────────────────────────
-- pgcrypto: gen_random_uuid(). vector: RAG embeddings (Phase 3).
-- pg_cron:  72h reminders / SLA timers (Phase 2). On Supabase these may also be
--           toggled in Dashboard → Database → Extensions; the statements are
--           harmless if already enabled.
CREATE EXTENSION IF NOT EXISTS pgcrypto;
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pg_cron;

-- ── Reference / identity ─────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS users (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  email TEXT UNIQUE NOT NULL,
  name TEXT,
  role TEXT NOT NULL CHECK (role IN ('ops_manager','adjuster','siu','admin','viewer')),
  approval_limit NUMERIC(12,2) DEFAULT 0,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS sessions (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID REFERENCES users(id) ON DELETE CASCADE,
  jwt_id TEXT,
  ip INET,
  expires_at TIMESTAMPTZ
);

-- ── Claim aggregate (a projection of claim_events) ───────────────────────────
CREATE TABLE IF NOT EXISTS claims (
  id TEXT PRIMARY KEY,
  state TEXT NOT NULL CHECK (state IN (
    'RECEIVED','TRIAGE','INFO_PENDING','PLANNING','EXECUTING','FAILED',
    'COMPENSATING','REVIEW_PENDING','SETTLEMENT','CLOSED','DENIED',
    'WITHDRAWN','ESCALATED')),
  workflow TEXT CHECK (workflow IN ('W1','W2','W3','W4','W5')),
  line TEXT,
  peril TEXT,
  severity SMALLINT,
  fraud_score NUMERIC(3,2),
  confidence NUMERIC(3,2),
  completeness NUMERIC(3,2),
  amount_est NUMERIC(12,2),
  reserve NUMERIC(12,2) NOT NULL DEFAULT 0,
  paid NUMERIC(12,2) NOT NULL DEFAULT 0,
  claimant_id TEXT,
  policy_id TEXT,
  assignee UUID REFERENCES users(id),
  sla_at TIMESTAMPTZ,
  version INT NOT NULL DEFAULT 0,        -- optimistic lock
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS claims_by_state ON claims(state, updated_at DESC);
CREATE INDEX IF NOT EXISTS claims_by_claimant ON claims(claimant_id);

-- ── Episodic log: the event IS the transition (event-sourced core, thesis 5) ─
CREATE TABLE IF NOT EXISTS claim_events (
  id BIGSERIAL PRIMARY KEY,
  claim_id TEXT NOT NULL REFERENCES claims(id) ON DELETE CASCADE,
  ts TIMESTAMPTZ NOT NULL DEFAULT now(),
  type TEXT NOT NULL,
  v SMALLINT NOT NULL DEFAULT 1,
  actor JSONB NOT NULL DEFAULT '{}'::jsonb,   -- {kind, component|user_id}
  data JSONB NOT NULL DEFAULT '{}'::jsonb,
  trace_id TEXT
);
CREATE INDEX IF NOT EXISTS events_by_claim ON claim_events(claim_id, ts);
CREATE INDEX IF NOT EXISTS events_by_type ON claim_events(type, ts DESC);

CREATE TABLE IF NOT EXISTS conversations (
  id BIGSERIAL PRIMARY KEY,
  claim_id TEXT NOT NULL REFERENCES claims(id) ON DELETE CASCADE,
  ts TIMESTAMPTZ NOT NULL DEFAULT now(),
  direction TEXT CHECK (direction IN ('in','out')),
  channel TEXT,
  author TEXT,
  body TEXT,
  template_id TEXT
);
CREATE INDEX IF NOT EXISTS conversations_by_claim ON conversations(claim_id, ts);

CREATE TABLE IF NOT EXISTS workflow_executions (
  exec_id TEXT PRIMARY KEY,
  claim_id TEXT NOT NULL REFERENCES claims(id) ON DELETE CASCADE,
  workflow TEXT,
  engine_ref TEXT,                 -- LangGraph thread_id
  status TEXT,
  phase TEXT,
  replan_count SMALLINT NOT NULL DEFAULT 0,
  token_budget_used INT NOT NULL DEFAULT 0,
  started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  ended_at TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS wf_by_claim ON workflow_executions(claim_id);

-- ── First-class entities: tool calls, decisions, approvals (thesis 9) ────────
CREATE TABLE IF NOT EXISTS tool_calls (
  id BIGSERIAL PRIMARY KEY,
  exec_id TEXT REFERENCES workflow_executions(exec_id) ON DELETE CASCADE,
  claim_id TEXT REFERENCES claims(id) ON DELETE CASCADE,
  seq INT,
  tool TEXT NOT NULL,
  risk_tier SMALLINT,
  args JSONB,
  args_hash TEXT,
  idempotency_key TEXT UNIQUE,
  status TEXT,
  result JSONB,
  error_code TEXT,
  latency_ms INT,
  retries SMALLINT NOT NULL DEFAULT 0,
  cached BOOL NOT NULL DEFAULT false,
  ts TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS tool_calls_by_claim ON tool_calls(claim_id, ts);

CREATE TABLE IF NOT EXISTS agent_decisions (
  id BIGSERIAL PRIMARY KEY,
  claim_id TEXT NOT NULL REFERENCES claims(id) ON DELETE CASCADE,
  ts TIMESTAMPTZ NOT NULL DEFAULT now(),
  decision_type TEXT CHECK (decision_type IN ('classify','route','plan','tiebreak','action','extract')),
  model TEXT,
  prompt_hash TEXT,
  output JSONB,
  confidence NUMERIC(3,2),
  alternatives JSONB,
  citations JSONB,
  guardrails JSONB,                -- {schema_ok, citation_coverage, ...}
  rule_id TEXT,                    -- for route decisions (R-00..R-99)
  config_version INT,              -- config row that produced the routing decision
  tokens_in INT,
  tokens_out INT,
  latency_ms INT,
  trace_id TEXT
);
CREATE INDEX IF NOT EXISTS decisions_by_claim ON agent_decisions(claim_id, ts);

CREATE TABLE IF NOT EXISTS approvals (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  claim_id TEXT NOT NULL REFERENCES claims(id) ON DELETE CASCADE,
  requested_action JSONB NOT NULL,
  risk_tier SMALLINT,
  evidence_refs JSONB,
  confidence NUMERIC(3,2),
  status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','approved','modified','rejected')),
  sla_at TIMESTAMPTZ,
  resolved_by UUID REFERENCES users(id),
  resolution TEXT CHECK (resolution IN ('approve','modify','reject')),
  delta JSONB,                     -- structured diff captured on Modify
  reason_code TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  resolved_at TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS approvals_pending_by_sla ON approvals(status, sla_at);
CREATE INDEX IF NOT EXISTS approvals_by_claim ON approvals(claim_id);

-- ── Audit log: append-only (UPDATE/DELETE revoked below) ─────────────────────
CREATE TABLE IF NOT EXISTS audit_log (
  id BIGSERIAL PRIMARY KEY,
  ts TIMESTAMPTZ NOT NULL DEFAULT now(),
  actor TEXT,
  action TEXT,
  subject TEXT,
  before_hash TEXT,
  after_hash TEXT,
  ip INET
);
CREATE INDEX IF NOT EXISTS audit_by_day ON audit_log(ts);

CREATE TABLE IF NOT EXISTS documents (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  claim_id TEXT REFERENCES claims(id) ON DELETE CASCADE,
  s3_key TEXT,                     -- Supabase Storage object key
  mime TEXT,
  sha256 TEXT,
  source TEXT,
  extracted BOOL NOT NULL DEFAULT false,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS documents_by_claim ON documents(claim_id);

-- ── Hot-reloadable, versioned routing config (thesis 2) ──────────────────────
CREATE TABLE IF NOT EXISTS config (
  id BIGSERIAL PRIMARY KEY,
  key TEXT NOT NULL,               -- e.g. 'routing'
  version INT NOT NULL,
  value JSONB NOT NULL,
  activated_by TEXT,
  activated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  active BOOL NOT NULL DEFAULT true,
  UNIQUE (key, version)
);
-- Only one active row per key.
CREATE UNIQUE INDEX IF NOT EXISTS config_one_active
  ON config(key) WHERE active;

-- ── LLM free-tier usage counters (RPD budget meter) ──────────────────────────
CREATE TABLE IF NOT EXISTS llm_usage (
  day DATE NOT NULL DEFAULT CURRENT_DATE,
  model TEXT NOT NULL,
  requests INT NOT NULL DEFAULT 0,
  tokens_in BIGINT NOT NULL DEFAULT 0,
  tokens_out BIGINT NOT NULL DEFAULT 0,
  PRIMARY KEY (day, model)
);

-- ── Seed the default routing config (R-00..R-99 thresholds) ──────────────────
INSERT INTO config (key, version, value, activated_by)
VALUES ('routing', 1, '{
  "auto_pay_ceiling": 2500,
  "fraud_low": 0.30,
  "fraud_high": 0.70,
  "severity_stp_max": 2,
  "coverage_conf_min": 0.85,
  "stp_confidence_min": 0.85,
  "completeness_min": 0.90,
  "field_conf_min": 0.80,
  "exclusion_conf_min": 0.90,
  "high_severity_min": 4,
  "high_amount_min": 25000,
  "coverage_conf_low": 0.60
}'::jsonb, 'migration:001')
ON CONFLICT (key, version) DO NOTHING;

-- ╔══════════════════════════════════════════════════════════════════════════╗
-- ║ Row-Level Security                                                          ║
-- ║ Model: the agent service uses the Supabase SERVICE-ROLE key, which bypasses ║
-- ║ RLS entirely (it is the trusted writer). RLS governs only browser access    ║
-- ║ via the anon/authenticated keys: everyone may READ (public viewer mode),    ║
-- ║ only authenticated operator-class users may WRITE.                          ║
-- ╚══════════════════════════════════════════════════════════════════════════╝

-- Role of the current request, derived from the users table by auth.uid().
-- Defaults to 'viewer' for anon / unmapped users.
CREATE OR REPLACE FUNCTION public.current_app_role() RETURNS TEXT
LANGUAGE sql STABLE AS $$
  SELECT COALESCE(
    (SELECT role FROM public.users WHERE id = auth.uid()),
    'viewer'
  );
$$;

CREATE OR REPLACE FUNCTION public.is_operator() RETURNS BOOLEAN
LANGUAGE sql STABLE AS $$
  SELECT public.current_app_role() IN ('ops_manager','adjuster','siu','admin');
$$;

DO $$
DECLARE t TEXT;
BEGIN
  FOREACH t IN ARRAY ARRAY[
    'users','sessions','claims','claim_events','conversations',
    'workflow_executions','tool_calls','agent_decisions','approvals',
    'audit_log','documents','config','llm_usage'
  ] LOOP
    EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY;', t);

    -- Public read (viewer mode). Drop-then-create for idempotency.
    EXECUTE format('DROP POLICY IF EXISTS %I ON %I;', t || '_read', t);
    EXECUTE format(
      'CREATE POLICY %I ON %I FOR SELECT TO anon, authenticated USING (true);',
      t || '_read', t);

    -- Operator write (INSERT/UPDATE). audit_log is append-only (no UPDATE).
    EXECUTE format('DROP POLICY IF EXISTS %I ON %I;', t || '_write', t);
    EXECUTE format(
      'CREATE POLICY %I ON %I FOR INSERT TO authenticated WITH CHECK (public.is_operator());',
      t || '_write', t);

    IF t <> 'audit_log' THEN
      EXECUTE format('DROP POLICY IF EXISTS %I ON %I;', t || '_update', t);
      EXECUTE format(
        'CREATE POLICY %I ON %I FOR UPDATE TO authenticated USING (public.is_operator());',
        t || '_update', t);
    END IF;
  END LOOP;
END $$;

-- Audit log is immutable from the app role: no UPDATE / DELETE, ever.
REVOKE UPDATE, DELETE ON audit_log FROM anon, authenticated;

-- ── Realtime: publish claim_events (+ projections) to the dashboard ──────────
-- Supabase creates the supabase_realtime publication; add our tables to it.
DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_publication WHERE pubname = 'supabase_realtime') THEN
    ALTER PUBLICATION supabase_realtime ADD TABLE claim_events;
    ALTER PUBLICATION supabase_realtime ADD TABLE claims;
    ALTER PUBLICATION supabase_realtime ADD TABLE tool_calls;
    ALTER PUBLICATION supabase_realtime ADD TABLE agent_decisions;
    ALTER PUBLICATION supabase_realtime ADD TABLE approvals;
  END IF;
EXCEPTION WHEN duplicate_object THEN
  NULL;  -- tables already in the publication
END $$;
