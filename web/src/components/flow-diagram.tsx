"use client";

import type { ClaimDetail } from "@/lib/types";

// Fixed lifecycle layout. The agent's spine is deterministic, so the diagram is
// a known graph; we just light up nodes/edges as the claim's events arrive.
const PIPE = [
  { key: "input", x: 16, label: "FNOL message", sub: "your text" },
  { key: "intake", x: 150, label: "Intake", sub: "normalize" },
  { key: "extract", x: 250, label: "Extract", sub: "Gemini" },
  { key: "classify", x: 372, label: "Classify", sub: "Gemini" },
  { key: "investigate", x: 494, label: "Investigate", sub: "tools · RAG" },
  { key: "route", x: 642, label: "Router", sub: "rules R-00..99" },
] as const;
const PIPE_W: Record<string, number> = {
  input: 120, intake: 86, extract: 108, classify: 108, investigate: 134, route: 116,
};
const CY = 200;

const LANES = [
  { wf: "W1", label: "W1 · STP", term: "CLOSED · paid" },
  { wf: "W2", label: "W2 · adjudicate", term: "REVIEW → DENIED/SETTLED" },
  { wf: "W3", label: "W3 · fraud (SIU)", term: "ESCALATED · no payment" },
  { wf: "W4", label: "W4 · info request", term: "INFO_PENDING" },
  { wf: "W5", label: "W5 · high-severity", term: "ESCALATED · senior" },
];
const LANE_X = 800;
const LANE_W = 120;
const TERM_X = 944;
const TERM_W = 126;
const laneY = (i: number) => 30 + i * 64; // top of lane box
const LANE_H = 46;
const laneCY = (i: number) => laneY(i) + LANE_H / 2;

const INFRA = [
  { label: "Gemini", sub: "flash-lite / flash" },
  { label: "Supabase", sub: "events · checkpoints" },
  { label: "Tool registry", sub: "schema · risk tiers" },
  { label: "pgvector", sub: "guideline RAG" },
];

interface Derived {
  reached: Set<string>;
  workflow: string | null;
  rule: string | null;
  state: string;
  terminalReached: boolean;
}

const EV_STAGE: Record<string, string> = {
  "claim.received": "intake",
  "claim.extracted": "extract",
  "claim.classified": "classify",
  "claim.investigated": "investigate",
  "claim.routed": "route",
};

function derive(detail: ClaimDetail | null): Derived {
  const reached = new Set<string>();
  let workflow: string | null = null;
  let rule: string | null = null;
  if (!detail) return { reached, workflow, rule, state: "—", terminalReached: false };
  reached.add("input");
  for (const e of detail.events) {
    const s = EV_STAGE[e.type];
    if (s) reached.add(s);
    if (e.type === "claim.routed") {
      workflow = (e.data.workflow as string) ?? workflow;
      rule = (e.data.rule_id as string) ?? rule;
    }
  }
  const state = detail.claim.state;
  workflow = detail.claim.workflow ?? workflow;
  const terminalReached = ["CLOSED", "DENIED", "ESCALATED", "WITHDRAWN"].includes(state);
  return { reached, workflow, rule, state, terminalReached };
}

function termColor(state: string): string {
  if (state === "CLOSED") return "#34d399"; // emerald
  if (state === "DENIED" || state === "ESCALATED") return "#f87171"; // red
  if (state === "REVIEW_PENDING") return "#fbbf24"; // amber
  if (state === "INFO_PENDING") return "#a78bfa"; // violet
  return "hsl(var(--muted-foreground))";
}

function Node({
  x, y, w, h = 46, label, sub, state,
}: {
  x: number; y: number; w: number; h?: number; label: string; sub?: string;
  state: "idle" | "done" | "active";
}) {
  const stroke = state === "idle" ? "hsl(var(--border))" : "hsl(var(--primary))";
  const fill = state === "idle" ? "hsl(var(--card))" : "hsl(var(--primary) / 0.18)";
  return (
    <g className={state === "active" ? "fd-node-active" : undefined}>
      <rect x={x} y={y} width={w} height={h} rx={8} fill={fill} stroke={stroke} strokeWidth={state === "idle" ? 1 : 2} />
      <text x={x + w / 2} y={y + (sub ? 19 : 27)} textAnchor="middle" fontSize="13" fontWeight="600" fill="hsl(var(--foreground))">{label}</text>
      {sub && <text x={x + w / 2} y={y + 34} textAnchor="middle" fontSize="10" fill="hsl(var(--muted-foreground))">{sub}</text>}
    </g>
  );
}

export function FlowDiagram({ detail }: { detail: ClaimDetail | null }) {
  const d = derive(detail);
  const order = ["input", "intake", "extract", "classify", "investigate", "route"];
  const lastPipe = [...order].reverse().find((k) => d.reached.has(k)) ?? null;
  const pipeActive = !d.workflow ? lastPipe : null; // pulse the frontier until routed

  const pipeState = (k: string): "idle" | "done" | "active" =>
    k === pipeActive ? "active" : d.reached.has(k) ? "done" : "idle";

  return (
    <div className="w-full overflow-x-auto rounded-lg border border-border bg-card/40 p-3">
      <svg viewBox="0 0 1080 360" className="w-full" style={{ minWidth: 760 }}>
        {/* pipeline edges */}
        {order.slice(0, -1).map((k, i) => {
          const a = PIPE.find((p) => p.key === k)!;
          const b = PIPE.find((p) => p.key === order[i + 1])!;
          const x1 = a.x + PIPE_W[a.key];
          const x2 = b.x;
          const on = d.reached.has(order[i + 1]);
          return (
            <line key={k} x1={x1} y1={CY + 23} x2={x2} y2={CY + 23}
              stroke={on ? "hsl(var(--primary))" : "hsl(var(--border))"} strokeWidth={on ? 2.5 : 1.5}
              className={on && !d.workflow && order[i + 1] === pipeActive ? "fd-edge-active" : undefined} />
          );
        })}

        {/* router -> lane edges */}
        {LANES.map((ln, i) => {
          const chosen = d.workflow === ln.wf;
          const x1 = PIPE[5].x + PIPE_W.route;
          return (
            <line key={ln.wf} x1={x1} y1={CY + 23} x2={LANE_X} y2={laneCY(i)}
              stroke={chosen ? "hsl(var(--primary))" : "hsl(var(--border))"}
              strokeWidth={chosen ? 2.5 : 1} opacity={chosen ? 1 : 0.35}
              className={chosen && !d.terminalReached ? "fd-edge-active" : undefined} />
          );
        })}

        {/* lane -> terminal edges */}
        {LANES.map((ln, i) => {
          const chosen = d.workflow === ln.wf;
          return (
            <line key={ln.wf} x1={LANE_X + LANE_W} y1={laneCY(i)} x2={TERM_X} y2={laneCY(i)}
              stroke={chosen ? termColor(d.state) : "hsl(var(--border))"} strokeWidth={chosen ? 2.5 : 1}
              opacity={chosen ? 1 : 0.3} />
          );
        })}

        {/* pipeline nodes */}
        {PIPE.map((p) => (
          <Node key={p.key} x={p.x} y={CY} w={PIPE_W[p.key]} label={p.label} sub={p.sub} state={pipeState(p.key)} />
        ))}

        {/* router rule badge */}
        {d.rule && (
          <text x={PIPE[5].x + PIPE_W.route / 2} y={CY - 8} textAnchor="middle" fontSize="11" fontWeight="700" fill="hsl(var(--primary))">
            {d.rule} → {d.workflow}
          </text>
        )}

        {/* lanes + terminals */}
        {LANES.map((ln, i) => {
          const chosen = d.workflow === ln.wf;
          const laneState: "idle" | "done" | "active" = chosen ? (d.terminalReached || d.state === "REVIEW_PENDING" || d.state === "INFO_PENDING" ? "done" : "active") : "idle";
          return (
            <g key={ln.wf} opacity={chosen || !d.workflow ? 1 : 0.32}>
              <Node x={LANE_X} y={laneY(i)} w={LANE_W} h={LANE_H} label={ln.label} state={laneState} />
              <g>
                <rect x={TERM_X} y={laneY(i)} width={TERM_W} height={LANE_H} rx={8}
                  fill={chosen ? `${termColor(d.state)}22` : "hsl(var(--card))"}
                  stroke={chosen ? termColor(d.state) : "hsl(var(--border))"} strokeWidth={chosen ? 2 : 1} />
                <text x={TERM_X + TERM_W / 2} y={laneY(i) + 28} textAnchor="middle" fontSize="10.5"
                  fill={chosen ? termColor(d.state) : "hsl(var(--muted-foreground))"}>{ln.term}</text>
              </g>
            </g>
          );
        })}

        {/* infra band (what the orchestrator commands) */}
        <text x={16} y={330} fontSize="10" fill="hsl(var(--muted-foreground))">Orchestrated services (the agent calls these; they never call it):</text>
        {INFRA.map((s, i) => (
          <g key={s.label}>
            <rect x={16 + i * 200} y={336} width={186} height={20} rx={5} fill="hsl(var(--muted) / 0.4)" stroke="hsl(var(--border))" />
            <text x={16 + i * 200 + 8} y={350} fontSize="10.5" fill="hsl(var(--foreground))">
              {s.label} <tspan fill="hsl(var(--muted-foreground))">· {s.sub}</tspan>
            </text>
          </g>
        ))}
      </svg>
    </div>
  );
}
