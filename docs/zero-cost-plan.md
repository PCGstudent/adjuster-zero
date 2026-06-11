# Adjuster Zero — Plano de Execução Custo-Zero (v2)

**Companion do blueprint principal. Adapta o projeto aos teus constrangimentos reais: orçamento ~€0/mês, Gemini API gratuita, demo sempre viva para mostrar em entrevistas de AI Lead, e máximo de aprendizagem pelo caminho.**

---

## 0. O Que Muda — e o Veredicto

Os teus constrangimentos novos: (1) custo mensal ~zero, sustentado durante meses; (2) tens Gemini API gratuita; (3) a demo tem de estar **viva e acessível a qualquer momento** numa entrevista; (4) queres aprender as ferramentas que vão aparecer nas entrevistas de AI Lead, não só montar infraestrutura.

**Veredicto: a ideia mantém-se — Adjuster Zero ganha ainda mais sob estes constrangimentos.** O critério decisivo da Parte 1 era "demonstrável com dados 100% sintéticos", e isso agora vale dobrado: dados sintéticos significam **zero custos de APIs externas** (tudo mockado), **zero risco de privacidade** (podes usar o free tier do Gemini sem preocupações — atenção: nos planos gratuitos a Google pode usar os dados para treino, o que com dados sintéticos é irrelevante e com dados reais seria inaceitável; saber dizer isto numa entrevista é, por si só, um sinal de maturidade), e uma demo que controlas a 100%.

O que muda é a **stack de implementação**. O desenho AWS da Parte 5 continua a ser o "perfil de produção" documentado no README — mas o deployment vivo passa para uma stack genuinamente gratuita e, importante, mais alinhada com o que se pergunta hoje em entrevistas de AI Lead.

---

## 1. Decisão de Stack

### A recomendação

| Camada | Escolha | Custo |
|---|---|---|
| Frontend (Cabine de Vidro) | **Next.js no Vercel** (plano Hobby) | €0 |
| Serviço do agente | **Python + FastAPI + LangGraph**, container no **Google Cloud Run** (scale-to-zero) | €0 dentro do free tier |
| LLM | **Gemini 2.5 Flash + Flash-Lite** (free tier), structured outputs nativos | €0 |
| Base de dados / Auth / Realtime / Storage | **Supabase Free** (Postgres — o esquema SQL da Parte 6 já está escrito!) | €0 |
| Estado durável do agente + HITL | **LangGraph PostgresSaver** (checkpoints no mesmo Supabase) | €0 |
| RAG | **pgvector no Supabase** + `gemini-embedding-001` | €0 |
| Observabilidade LLM | **LangSmith Free** (ou Langfuse Cloud Free como alternativa open-source) | €0 |
| CI + evals agendados + keep-alive | **GitHub Actions** (repo público = minutos ilimitados) | €0 |
| Único custo real (opcional) | Domínio próprio (`adjusterzero.dev` ou similar) | ~€10/ano |

### Porquê LangGraph e não Step Functions (a resposta honesta)

Para um cargo de **AI Lead em 2026**, LangGraph é a palavra-chave de maior sinal: é o framework sobre o qual te vão fazer perguntas, e implementa nativamente exatamente os conceitos do blueprint — `StateGraph` com estado tipado, `conditional_edges` (o roteador!), checkpointers (persistência de estado!), `interrupt()` (humano-no-loop!). E há uma simetria que vira ouro em entrevista: **`interrupt()` + checkpointer Postgres é o mesmo padrão que `waitForTaskToken` do Step Functions** — execução pausa, estado persiste a custo zero, humano aprova, `Command(resume=...)` retoma. Saber dizer "é o mesmo padrão, duas implementações; eis o mapeamento entre as duas stacks" demonstra que percebes o *padrão*, não só a ferramenta.

A tese central do blueprint não muda nada: **o LLM propõe, o orquestrador dispõe.** O LangGraph é o executor; a tabela de regras R-00…R-99 continua a viver numa função pura determinística chamada pela conditional edge. O roteamento continua a não ser "feeling".

### Mapeamento AWS → Custo-Zero (vai direto para o README)

| Perfil de produção (Parte 5) | Perfil custo-zero (vivo) | Padrão preservado |
|---|---|---|
| Step Functions Standard + waitForTaskToken | LangGraph + PostgresSaver + interrupt() | Máquina de estados durável, HITL |
| DynamoDB tabela única | Postgres (Supabase) — esquema relacional da Parte 6 | Decisões/ferramentas/aprovações como entidades de 1ª classe |
| SQS + DLQ | Tabela de fila no Postgres (ou pgmq) com `status=dead` | Desacoplamento, mensagens envenenadas inspecionáveis |
| EventBridge bus | Tabela `claim_events` + **Supabase Realtime** → dashboard ao vivo | Event-sourcing, feed do cockpit |
| EventBridge Scheduler | `pg_cron` no Supabase + GitHub Actions cron | Lembretes 72h, timers de SLA |
| OpenSearch | pgvector (híbrido: full-text do Postgres + kNN) | RAG com citações |
| Bedrock | Gemini API (structured outputs `responseSchema` = a validação de esquema do blueprint) | Saídas tipadas, reparação 1× |
| CloudWatch + X-Ray | LangSmith/Langfuse + logs do Cloud Run + decision log próprio | Traces ponta-a-ponta por `trace_id` |
| Cognito | Supabase Auth (+ RLS para o modo visitante read-only) | Auth, papéis |
| S3 | Supabase Storage | Documentos do FNOL |

### E a opção AWS, já agora?

É viável quase grátis, mas com asteriscos: desde meados de 2025 as contas novas AWS funcionam por créditos (~US$100 à entrada, até mais ~US$100 por atividades, plano gratuito limitado a ~6 meses); depois disso, no plano pago, os always-free (Lambda 1M req/mês, DynamoDB 25GB, Step Functions 4 000 transições/mês) continuam a cobrir o volume de demo por cêntimos — mas há risco de fatura-surpresa para quem está a começar (CloudWatch, ECR, NAT por engano). **Recomendação: AWS fica como "perfil de produção" documentado, com o diagrama da Parte 5 no README; opcionalmente, na semana 4+, usa os créditos para um mini-deploy de uma state machine no Step Functions só para screenshots e para poderes dizer "também o corri lá".** O deployment que tem de sobreviver meses sem vigilância fica na stack custo-zero, onde os planos gratuitos limitam em vez de faturar.

---

## 2. Arquitetura Custo-Zero

```
  Navegador (entrevistador a ver / tu a conduzir)
       │
       ├──HTTPS──► Vercel: Next.js (Cabine de Vidro, Inbox de Aprovação,
       │           Analytics, botões de cenário de demo)
       │                │ subscribe (WebSocket)
       │                ▼
       │           Supabase Realtime ◄── INSERT em claim_events (cada transição)
       │
       └──HTTPS /api──► Cloud Run: FastAPI + LangGraph
                          │
            ┌─────────────┼───────────────────────────────┐
            ▼             ▼                               ▼
      Gemini API     Supabase Postgres               LangSmith/Langfuse
      (free tier)    · esquema Parte 6 (claims,      (traces de cada
      · 2.5 Flash      events, decisions, tool_calls, chamada LLM e
        (planos,       approvals, audit)              execução do grafo)
        desempates)  · checkpoints LangGraph (HITL)
      · Flash-Lite   · pgvector (diretrizes RAG)
        (extração,   · fila Postgres + pg_cron
        classific.)  · RLS: papel "viewer" read-only
      · embedding-001
                          ▲
  GitHub Actions ─────────┘
  · cron diário: keep-alive Supabase + ping Cloud Run
  · cron semanal: harness de evals (golden set) → relatório no repo
  · CI: testes do roteador + validação de esquemas
```

**Como o grafo LangGraph mapeia o blueprint:**

- **Nós** = fases: `intake → extract → classify → route → [W1|W2|W3|W4|W5 sub-fluxos] → settle → close`.
- **`conditional_edges`** = o Motor de Decisão: uma função pura `route(state) → "W1".."W5"` que implementa a tabela R-00…R-99 lida da config em Postgres (hot-reload preservado). O desempate R-06 é o único nó que chama o LLM para rotear — e grava a decisão com alternativas, como no blueprint.
- **Estado do grafo** = o Agregado de Sinistro (Pydantic), serializado pelo checkpointer — a "memória de trabalho" da Parte 3, de borla.
- **`interrupt()`** = a Camada de Aprovação Humana: o nó de portão N1/N2 interrompe; o endpoint `/approvals/{id}/resolve` faz `graph.invoke(Command(resume={...}))`; o delta de modificação grava-se em `approvals.delta`. Sinistro pode ficar dias em REVIEW_PENDING a custo zero (Cloud Run está a dormir; o estado está no Postgres).
- **Camada de ferramentas** = registo próprio (dict de Pydantic models por ferramenta, com `risk_tier`, validação in/out, idempotency keys) — **não** uses tool-calling "solto"; o Executor valida cada passo contra a allow-list do fluxo antes de executar, exatamente como na Parte 4.
- **Streaming de eventos**: cada transição de nó e cada tool call escreve em `claim_events` → Realtime empurra para o cockpit → o entrevistador vê o agente a pensar **ao vivo, sem refresh**. Este é o upgrade visual mais barato e mais impressionante de toda a stack.

---

## 3. Orçamento, Limites e a Matemática do Free Tier

### Limites que importam (à data desta escrita — confirma em ai.google.dev e nas páginas de pricing; free tiers mudam)

| Serviço | Limite relevante | Implicação de design |
|---|---|---|
| Gemini 2.5 Flash (free) | ~10 RPM, ~250 pedidos/dia | Modelo "caro": só planos, desempates R-06, cartas |
| Gemini 2.5 Flash-Lite (free) | ~15 RPM, ~1 000/dia | Modelo por omissão: extração, classificação, sinais de fraude |
| gemini-embedding-001 (free) | suficiente p/ corpus pequeno | Embeddings do corpus 1×; queries são baratas |
| Supabase Free | 500 MB DB; **pausa após ~7 dias sem atividade** | Keep-alive diário via Actions (query trivial) |
| Cloud Run free | ~2M requests/mês + generoso em vCPU-s; scale-to-zero | Cold start de 2–5 s; ping antes da entrevista |
| Vercel Hobby | uso não-comercial, largura de banda limitada | Portfólio pessoal = ok |
| LangSmith Free | ~5 000 traces/mês | Chega para meses de demo; Langfuse Free (~50k) se precisares de mais |
| GitHub Actions | grátis em repo público | Evals, keep-alive, CI — tudo aqui |

### A matemática por sinistro (e porque os limites são uma *feature*)

Pipeline típico: 1 extração + 1 classificação + 1 plano + 0–1 fraude-LLM + 0–1 desempate + 1 carta ≈ **4–6 chamadas LLM por sinistro**, das quais só 1–2 precisam do Flash "grande".

- **Ao vivo (entrevista):** 1 sinistro de cada vez → ~5 chamadas em ~90 s → muito abaixo de 10 RPM. Folga total.
- **Em lote (encher o dashboard):** a 10–15 RPM sustentados ≈ 2–3 sinistros/minuto. Injetar 20 sinistros = ~8 min de fila visível — e é aqui que os limites viram feature: implementa um **limitador central (token bucket) + fila de admissão**, e o cockpit mostra "em fila (rate limit do fornecedor)". Numa entrevista, isso chama-se *admission control* e é arquitetura de produção, não uma desculpa.
- **Orçamento diário:** ~250/dia no Flash + ~1 000/dia no Flash-Lite ≈ **60–120 sinistros completos/dia**. O teu golden set de evals (50 sinistros × ~5 chamadas = ~250) consumiria o dia inteiro do Flash — por isso os **evals correm semanalmente** (GitHub Actions, domingo à noite), maioritariamente em Flash-Lite, e há um **contador de orçamento RPD no ecrã de Admin** para nunca chegares a uma entrevista com a quota gasta.
- **Resiliência a 429:** retry com backoff exponencial + downgrade automático Flash→Flash-Lite no segundo falhanço + estado "rate-limited, retrying" visível na timeline. Um 429 a meio da demo torna-se uma demonstração de observabilidade em vez de um silêncio embaraçoso.

### Custo total honesto

€0/mês de infraestrutura e LLM dentro dos planos gratuitos. Único custo recomendado: ~€10/ano de domínio (opcional — `*.vercel.app` serve). Configura na mesma um **alerta de orçamento de €1 no GCP** e exporta a fatura mensal para o README ("custo real do último mês: €0,00" é uma linha deliciosa num portfólio).

---

## 4. Roadmap Revisto — 4 Fins de Semana Nesta Stack

A disciplina mantém-se: a fatia vertical fica viva no fim de semana 1 e nunca mais parte. Cada semana inclui agora o **objetivo de aprendizagem** explícito — é isso que vais saber responder em entrevista.

### Fim de semana 1 — Fatia vertical viva
**Constróis:** repo público (monorepo: `/web`, `/agent`, `/evals`, `/db`); esquema SQL da Parte 6 aplicado no Supabase; gerador de dados sintéticos v0 (apólices, requerentes, 3 cenários de FNOL parametrizados — limpo, apólice caducada, docs em falta); grafo LangGraph mínimo (`intake → extract → classify → route → executar W1 → settle`) com PostgresSaver; 5 ferramentas mock com Pydantic (`policy_lookup`, `coverage_check` stub, `repair_cost_estimator`, `payment_execute` idempotente, `customer_comm_send` em rascunho); structured outputs do Gemini com validação + 1 retry de reparação; dashboard Next.js com fila + timeline alimentada por Supabase Realtime; **deploy no dia 2** (Cloud Run + Vercel) com keep-alive no Actions.
**Demo de fim de semana:** Jornada A ao vivo, ponta-a-ponta, no URL público.
**Aprendes:** StateGraph, checkpointers, structured outputs com `responseSchema`, porque é que validação de esquema é o guardrail mais barato que existe.

### Fim de semana 2 — Roteamento real, humanos reais
**Constróis:** tabela de regras completa R-00…R-99 como função pura **com testes unitários** (CI no Actions); registo de ferramentas com `risk_tier` N0/N1/N2 e allow-lists por fluxo; fluxos W2 e W4 (W5 = stub escalar-com-pacote); `interrupt()` no portão N1/N2 + Inbox de Aprovação com aprovar/modificar/rejeitar e captura de delta; `pg_cron` para lembretes 72h e timers de SLA; limitador de débito + fila de admissão para o Gemini.
**Demo:** Jornadas B (a recusa, com cláusula citada) e D (o dia do aprovador).
**Aprendes:** HITL durável com interrupt/resume — e a frase "é o waitForTaskToken do Step Functions, implementado em LangGraph".

### Fim de semana 3 — Fundamentação, fraude e a Cabine de Vidro completa
**Constróis:** corpus de ~12 diretrizes escritas por ti → chunking → embeddings → pgvector; `guideline_search` híbrido (full-text + kNN); `coverage_check` real com **citações obrigatórias** e validação de cobertura de citação; duplicados semânticos + `weather_event_verify` + scan de fraude híbrido; desempate R-06 com alternativas registadas; LangSmith ligado (traces de grafo + LLM); decision log de 1ª classe renderizado no cockpit (confiança, alternativas, citações, o que o agente decidiu *não* fazer); Console do Agente (stream Realtime global).
**Demo:** Jornada C — a captura de fraude com evidências no ecrã.
**Aprendes:** RAG como serviço de fundamentação de decisões (não chat), enforcement de citações, tracing de agentes.

### Fim de semana 4 — Confiança, evals e a camada de vendas
**Constróis:** harness de evals (golden set de 50 sinistros rotulados; corre semanal no Actions + botão "Run Evals" no Admin; matriz de confusão de rotas e taxa de aprovação gravadas em Postgres); gráfico de calibração (semeia-o adjudicando tu ~60 aprovações sintéticas); medidor de custo-por-sinistro e de orçamento RPD; hardening (reconciliar-antes-de-retentar no pagamento, orçamento de tokens e de replans por sinistro, modo degradado "sem STP com controlo de fraude em baixo"); **playbook de demo** (secção 5); README com o pitch, o diagrama, a tabela de mapeamento AWS↔custo-zero e o doc "o que o LLM não tem permissão de fazer"; vídeo de 3 minutos.
**Demo:** o guião completo de entrevista, cronometrado.
**Aprendes:** avaliação de agentes (a competência mais rara do mercado), calibração de confiança, e a arte de transformar um projeto em narrativa.

**Se um fim de semana evaporar, corta por esta ordem:** semeadura da calibração → lembretes W4 → Console do Agente → duplicados semânticos. **Nunca cortes:** o checkpointer, a Inbox de Aprovação, o decision log, a Jornada B.

---

## 5. Playbook de Demo para Entrevistas

### Checklist T-30 minutos
1. Disparar o workflow "warm-up" no Actions (ping Cloud Run + query Supabase + 1 chamada Gemini de teste).
2. Botão "Reset demo" no Admin: limpa sinistros de demonstração, mantém histórico/analytics.
3. Verificar o contador de orçamento RPD (> 60 chamadas disponíveis).
4. Abrir 3 separadores: Fila de Sinistros, Inbox de Aprovação, Analytics. Login de aprovador feito.
5. Plano B pronto: vídeo de 3 min e GIFs no README; Plano C: `docker-compose up` local.

### O guião de 7 minutos
- **0:00–0:30** — Fila vazia. Uma frase de enquadramento: "Isto é um departamento de sinistros autónomo com rasto de auditoria. Vou injetar três sinistros e vocês vão ver o agente decidir."
- **0:30–2:30** — Botão **"Injetar sinistro limpo"**. Narras o cockpit em tempo real: extração com confiança por campo, classificação com alternativas, "regra R-03 disparou → W1", as 6 tool calls, o portão de política, o pagamento, o sinistro FECHADO em ~90 s. Apontas para o que o agente decidiu *não* fazer.
- **2:30–4:00** — Botão **"Injetar apólice caducada"**. O momento de confiança: o agente recusa, cita a cláusula, e *mesmo assim* pede aprovação humana porque negar é consequente. Aprovas ao vivo na Inbox — e mostras o `interrupt/resume` a acontecer.
- **4:00–5:30** — Botão **"Injetar suspeita de fraude"**. Score 0.81, sinais com evidência, rota W3, e a frase: "deste estado, o caminho de pagamento é inalcançável — por construção, não por prompt."
- **5:30–7:00** — Ecrã de Analytics: taxa de STP, taxa de override, **gráfico de calibração**, custo por sinistro. Fechas com: "tudo isto corre a €0/mês; eis o desenho equivalente em AWS para escala empresarial" (README aberto na tabela de mapeamento).

### Modo visitante
Link público read-only (RLS no Supabase, papel `viewer`): o recruiter pode explorar sozinho depois da entrevista. Mete o link no CV e no LinkedIn — o portfólio trabalha enquanto dormes.

---

## 6. Pergunta de Entrevista → Onde Está a Resposta no Projeto

| Pergunta provável | A tua resposta apontando para o projeto |
|---|---|
| "Como evitas que o agente entre em loop?" | Máx. 2 replans por sinistro + orçamento de tokens por sinistro, impostos pelo Executor; esgotar = escalar (mostra o código do portão) |
| "O que acontece quando o LLM erra?" | Tiers N0/N1/N2, validação de esquema com 1 reparação, citações obrigatórias, calibração pública, compensação no pagamento — o erro é barato, detetável e reversível |
| "Porque LangGraph e não Step Functions / Temporal?" | Tabela de mapeamento no README; "mesmo padrão, duas implementações; escolhi a que mantém a demo viva a €0 e documentei a migração" |
| "Como decides que workflow seguir?" | Tabela R-00…R-99 determinística com testes unitários; LLM só desempata a faixa ambígua e fica registado com alternativas — roteamento é política, não feeling |
| "Como avalias o agente?" | Golden set de 50, evals semanais no CI, matriz de confusão de rotas, taxa de override por bucket de confiança |
| "Humano-no-loop, como?" | interrupt() + checkpointer; sinistro pausado dias a custo zero; deltas de modificação capturados como dados |
| "Custos em produção?" | Medidor de custo-por-sinistro no dashboard + escalonamento de modelos + caches; "sei onde está cada cêntimo" |
| "E privacidade/dados?" | Free tiers podem treinar com os dados → por isso o projeto é 100% sintético; em produção real, tier pago/VPC e o desenho AWS da Parte 5 |
| "Isto escala?" | Admission control já implementado (por causa do rate limit), tudo stateless + fila; perfil AWS documentado para volume real |

---

## 7. Armadilhas Práticas (vais bater nelas; melhor saber já)

1. **Supabase Free pausa após ~7 dias de inatividade.** O cron diário no Actions (uma query trivial) resolve. Sem isto, chegas à entrevista com a base de dados a dormir.
2. **Cold start do Cloud Run (2–5 s).** Aceitável em uso normal; antes de entrevistas, o warm-up do checklist. Não pagues min-instances.
3. **429 do Gemini a meio da demo.** Token bucket + retry com backoff + downgrade para Flash-Lite + estado visível na timeline. Ensaiado, vira talking point.
4. **Free tiers mudam sem aviso.** Abstrai o fornecedor LLM atrás de uma interface (um ficheiro): trocar Gemini por outro fornecedor é 1 PR. Revê limites 1×/mês.
5. **Vercel Hobby é "non-commercial".** Portfólio pessoal está dentro das regras; se um dia cobrares a clientes por isto, migra para o plano pago ou para Cloud Run também no frontend.
6. **Nunca metas dados reais no pipeline.** Nem "só para testar". O projeto inteiro está desenhado para não precisar.
7. **Alerta de faturação de €1 no GCP** no dia 1. A fatura €0,00 mensal vai para o README.
8. **Não uses tool-calling automático "solto" do framework para ações N1/N2.** O Executor valida cada passo contra a allow-list e exige `approval_ref`/`gate_ref` estruturalmente — é a tese do projeto; não a percas por conveniência do SDK.

---

## 8. Primeiros Passos — Esta Semana, Antes do Fim de Semana 1

1. Contas: Google AI Studio (chave Gemini), GCP (+ billing com alerta €1), Supabase, Vercel, LangSmith, repo GitHub **público**.
2. Aplicar o SQL da Parte 6 no Supabase (está pronto a colar); ativar pgvector e pg_cron.
3. "Olá, grafo": LangGraph com 2 nós + PostgresSaver a gravar checkpoints no Supabase — só para provar a canalização.
4. Deploy de um FastAPI vazio no Cloud Run e de um Next.js vazio no Vercel; ligar o keep-alive no Actions.
5. Colar o pitch do Apêndice do blueprint no README, com "🚧 a construir em público — semana 1/4". Construir em público é marketing gratuito para um AI Lead.

A partir daí, segue o roadmap da secção 4. O blueprint principal continua a ser a tua referência para o *quê* (fluxos, ferramentas, esquema, observabilidade); este documento é o *como* a custo zero.
