# Database — apply & verify (Supabase)

The agent service connects with the **service-role** key / `DATABASE_URL` and
bypasses RLS (it is the trusted writer). The browser uses the **anon** key and
is governed by RLS: everyone can read (public viewer mode), only authenticated
operator-class users can write.

## Apply the schema

> ⚠️ Migrations are applied by **you**, not the agent. The agent never runs DDL.

1. Open your Supabase project → **SQL Editor** → **New query**.
2. (First time only) Enable extensions if the SQL editor lacks permission for
   `CREATE EXTENSION`: **Database → Extensions** and toggle on `vector`,
   `pg_cron`, `pgcrypto`. (`001_init.sql` also tries to create them; toggling in
   the dashboard first avoids a permission error on some plans.)
3. Paste the entire contents of [`migrations/001_init.sql`](migrations/001_init.sql)
   and click **Run**.
4. Confirm tables exist: **Table Editor** should list `claims`, `claim_events`,
   `agent_decisions`, `approvals`, `tool_calls`, `config`, `llm_usage`, etc.

### …or via psql

```bash
psql "$DATABASE_URL" -f db/migrations/001_init.sql
```

## Verify the hello-graph checkpoint (Phase 0 acceptance)

After calling `POST /debug/hello-graph` against the running agent, LangGraph's
`PostgresSaver` will have created its checkpoint tables and written a row:

```sql
-- The checkpointer tables exist and hold the run you just executed:
SELECT thread_id, checkpoint_id
FROM   checkpoints
ORDER BY checkpoint_id DESC
LIMIT 5;
```

You should see a `thread_id` matching the one returned by the endpoint.

## Verify the LLM RPD counter (Phase 0 acceptance)

After calling `POST /debug/llm-echo`:

```sql
SELECT * FROM llm_usage WHERE day = CURRENT_DATE;
-- requests for gemini-2.5-flash-lite should increment by 1 per echo call.
```

## Notes on the connection string

Use the Supabase **Session pooler** connection string (port `5432`) for
`DATABASE_URL`. LangGraph's `PostgresSaver` uses prepared statements, which the
session pooler supports but the transaction pooler (port `6543`) does not.
