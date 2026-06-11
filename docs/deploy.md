# Deploy — Adjuster Zero (you run these; the agent never deploys itself)

Two deploy targets: the **agent** to Google Cloud Run, the **web** to Vercel.
Both are free-tier. Apply the DB schema first (see `db/README.md`).

## 0. Prerequisites (accounts you create)

| Account | Why | Where |
|---|---|---|
| Google AI Studio | `GEMINI_API_KEY` | https://aistudio.google.com/apikey |
| Supabase | Postgres + Auth + Realtime + Storage | https://supabase.com |
| Google Cloud | Cloud Run (agent) | https://console.cloud.google.com |
| Vercel | Next.js hosting | https://vercel.com |
| GitHub | repo + Actions (CI, keep-alive, evals) | https://github.com |

Set a **€1 budget alert** in GCP on day one (the €0,00 monthly bill is a README
line worth keeping honest).

## 1. Agent → Cloud Run

```bash
# From repo root. Replace PROJECT_ID / REGION.
gcloud config set project PROJECT_ID

# Build & deploy the container (Cloud Run builds from the Dockerfile in /agent).
gcloud run deploy adjuster-zero-agent \
  --source agent \
  --region europe-west1 \
  --allow-unauthenticated \
  --min-instances 0 \
  --set-env-vars "GEMINI_API_KEY=...,DATABASE_URL=...,SUPABASE_URL=...,SUPABASE_SERVICE_ROLE_KEY=..."
```

- `--min-instances 0` keeps scale-to-zero (cold start 2–5 s; warm up before demos).
- Prefer storing secrets in **Secret Manager** and referencing with
  `--set-secrets` instead of `--set-env-vars` for anything sensitive.
- The service reads `$PORT` (Cloud Run injects it); the Dockerfile honors it.

After deploy, note the service URL → it's `NEXT_PUBLIC_AGENT_URL` and the
keep-alive `AGENT_URL` secret.

## 2. Web → Vercel

1. Import the GitHub repo in Vercel; set **Root Directory = `web`**.
2. Environment variables (Project Settings → Environment Variables):
   - `NEXT_PUBLIC_SUPABASE_URL`
   - `NEXT_PUBLIC_SUPABASE_ANON_KEY`
   - `NEXT_PUBLIC_AGENT_URL` (the Cloud Run URL from step 1)
3. Deploy. Framework preset = Next.js (auto-detected).

## 3. GitHub Actions secrets

Repo → Settings → Secrets and variables → Actions:
`SUPABASE_URL`, `SUPABASE_ANON_KEY`, `AGENT_URL` (keep-alive), and
`GEMINI_API_KEY`, `DATABASE_URL` (weekly evals, Phase 4).

## 4. Verify

- `GET <agent-url>/healthz` → `{"status":"ok","db_reachable":true,...}`
- `POST <agent-url>/debug/hello-graph` → `checkpoint_persisted: true`
- Web status page shows both Supabase and Agent green.
