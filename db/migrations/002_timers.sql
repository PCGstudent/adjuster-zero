-- ╔══════════════════════════════════════════════════════════════════════════╗
-- ║ 002_timers.sql — pg_cron timers (blueprint Part 3 / EventBridge Scheduler   ║
-- ║ analogue). Each job WRITES AN EVENT (event-sourced), which Realtime pushes  ║
-- ║ to the dashboard. Apply after 001_init.sql. Requires the pg_cron extension. ║
-- ╚══════════════════════════════════════════════════════════════════════════╝

-- Re-running is safe: unschedule the jobs if they already exist, then schedule.
DO $$
BEGIN
  PERFORM cron.unschedule('adjuster_doc_reminders');
EXCEPTION WHEN OTHERS THEN NULL;
END $$;

DO $$
BEGIN
  PERFORM cron.unschedule('adjuster_approval_sla');
EXCEPTION WHEN OTHERS THEN NULL;
END $$;

-- 72h document reminders: claims sitting in INFO_PENDING for > 72h get a
-- reminder event (at most one per 24h). Hourly.
SELECT cron.schedule('adjuster_doc_reminders', '0 * * * *', $job$
  INSERT INTO claim_events (claim_id, type, actor, data)
  SELECT c.id, 'claim.reminder',
         '{"kind":"system","component":"scheduler"}'::jsonb,
         jsonb_build_object('reason', 'document_reminder', 'since', c.updated_at)
  FROM claims c
  WHERE c.state = 'INFO_PENDING'
    AND c.updated_at < now() - interval '72 hours'
    AND NOT EXISTS (
      SELECT 1 FROM claim_events e
      WHERE e.claim_id = c.id AND e.type = 'claim.reminder'
        AND e.ts > now() - interval '24 hours');
$job$);

-- Approval SLA flags: pending approvals past their SLA get a one-time breach
-- event. Every 15 minutes.
SELECT cron.schedule('adjuster_approval_sla', '*/15 * * * *', $job$
  INSERT INTO claim_events (claim_id, type, actor, data)
  SELECT a.claim_id, 'approval.sla_breach',
         '{"kind":"system","component":"scheduler"}'::jsonb,
         jsonb_build_object('approval_id', a.id, 'sla_at', a.sla_at)
  FROM approvals a
  WHERE a.status = 'pending' AND a.sla_at IS NOT NULL AND a.sla_at < now()
    AND NOT EXISTS (
      SELECT 1 FROM claim_events e
      WHERE e.claim_id = a.claim_id AND e.type = 'approval.sla_breach'
        AND e.data->>'approval_id' = a.id::text);
$job$);

-- Inspect scheduled jobs:  SELECT jobname, schedule FROM cron.job;
