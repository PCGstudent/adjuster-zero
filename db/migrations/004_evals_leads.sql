-- ╔══════════════════════════════════════════════════════════════════════════╗
-- ║ 004_evals_leads.sql — eval run history + contact-agent leads (Phase 4).     ║
-- ╚══════════════════════════════════════════════════════════════════════════╝

CREATE TABLE IF NOT EXISTS eval_runs (
  id BIGSERIAL PRIMARY KEY,
  ts TIMESTAMPTZ NOT NULL DEFAULT now(),
  total INT NOT NULL,
  route_accuracy NUMERIC(5,4),
  terminal_accuracy NUMERIC(5,4),
  report JSONB
);

-- The "Talk to me" contact form is itself a tiny agent; leads land here.
CREATE TABLE IF NOT EXISTS leads (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  ts TIMESTAMPTZ NOT NULL DEFAULT now(),
  name TEXT,
  email TEXT,
  message TEXT,
  process TEXT,            -- the prospect's process (claims/invoices/leads/tickets/...)
  qualified BOOL,
  clarifying_question TEXT,
  email_draft TEXT,
  trace_id TEXT
);

ALTER TABLE eval_runs ENABLE ROW LEVEL SECURITY;
ALTER TABLE leads ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS eval_runs_read ON eval_runs;
CREATE POLICY eval_runs_read ON eval_runs FOR SELECT TO anon, authenticated USING (true);

DROP POLICY IF EXISTS leads_read ON leads;
CREATE POLICY leads_read ON leads FOR SELECT TO anon, authenticated USING (true);

-- Realtime for the live eval/lead views.
DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_publication WHERE pubname = 'supabase_realtime') THEN
    ALTER PUBLICATION supabase_realtime ADD TABLE eval_runs;
    ALTER PUBLICATION supabase_realtime ADD TABLE leads;
  END IF;
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;
