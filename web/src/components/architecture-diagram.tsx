// Static, fully-annotated architecture diagram for the "How it works" page.
// Color-coded by actor so a reader sees at a glance where the LLM is allowed to
// act (it proposes) versus where deterministic code decides (it disposes).

const ACTOR_FILL: Record<string, string> = {
  det: "#38bdf8", // sky — deterministic
  lite: "#818cf8", // indigo — LLM flash-lite
  flash: "#a78bfa", // violet — LLM flash
  rag: "#34d399", // emerald — RAG
  human: "#fb7185", // rose — human gate
  term: "#94a3b8", // slate — terminal
};

function Box({
  x, y, w, h, title, sub, actor, n,
}: {
  x: number; y: number; w: number; h: number; title: string; sub?: string;
  actor: keyof typeof ACTOR_FILL; n?: number;
}) {
  const c = ACTOR_FILL[actor];
  return (
    <g>
      <rect x={x} y={y} width={w} height={h} rx={9} fill={`${c}22`} stroke={c} strokeWidth={1.6} />
      {n != null && (
        <>
          <circle cx={x + 13} cy={y + 13} r={9} fill={c} />
          <text x={x + 13} y={y + 17} textAnchor="middle" fontSize="11" fontWeight="800" fill="#0b1220">{n}</text>
        </>
      )}
      <text x={x + w / 2} y={y + (sub ? h / 2 - 1 : h / 2 + 4)} textAnchor="middle" fontSize="12.5" fontWeight="700" fill="#e2e8f0">{title}</text>
      {sub && <text x={x + w / 2} y={y + h / 2 + 14} textAnchor="middle" fontSize="9.5" fill="#94a3b8">{sub}</text>}
    </g>
  );
}

function Edge({ x1, y1, x2, y2, dash, color = "#475569" }: { x1: number; y1: number; x2: number; y2: number; dash?: boolean; color?: string }) {
  return <line x1={x1} y1={y1} x2={x2} y2={y2} stroke={color} strokeWidth={1.5} strokeDasharray={dash ? "5 4" : undefined} markerEnd="url(#arrow)" />;
}

export function ArchitectureDiagram() {
  return (
    <div className="overflow-x-auto rounded-lg border border-border bg-card/40 p-3">
      <svg viewBox="0 0 1120 640" className="w-full" style={{ minWidth: 880 }}>
        <defs>
          <marker id="arrow" markerWidth="8" markerHeight="8" refX="6" refY="3" orient="auto">
            <path d="M0,0 L6,3 L0,6 Z" fill="#64748b" />
          </marker>
        </defs>

        {/* TRIAGE pipeline (row 1) */}
        <Box x={16} y={40} w={120} h={48} title="FNOL in" sub="email/form/API" actor="det" n={0} />
        <Box x={166} y={40} w={96} h={48} title="Intake" sub="normalize" actor="det" />
        <Box x={292} y={40} w={120} h={48} title="Extract" sub="flash-lite" actor="lite" n={1} />
        <Box x={442} y={40} w={120} h={48} title="Classify" sub="flash-lite" actor="lite" n={2} />
        <Box x={592} y={40} w={150} h={48} title="Investigate" sub="tools · RAG · fraud" actor="det" n={3} />
        <Box x={772} y={40} w={120} h={48} title="Router" sub="pure rules" actor="det" n={4} />
        <Edge x1={136} y1={64} x2={166} y2={64} />
        <Edge x1={262} y1={64} x2={292} y2={64} />
        <Edge x1={412} y1={64} x2={442} y2={64} />
        <Edge x1={562} y1={64} x2={592} y2={64} />
        <Edge x1={742} y1={64} x2={772} y2={64} />

        {/* INVESTIGATE inside (row 2) */}
        <rect x={300} y={120} width={520} height={150} rx={10} fill="#0f172a" stroke="#334155" strokeDasharray="4 4" />
        <text x={312} y={138} fontSize="11" fontWeight="700" fill="#94a3b8">Inside “Investigate” — agentic RAG + fraud (the agent calls these)</text>
        <Edge x1={667} y1={88} x2={560} y2={120} dash />
        <Box x={312} y={150} w={120} h={40} title="policy_lookup" actor="det" />
        <Box x={312} y={200} w={120} h={40} title="repair_estimate" actor="det" />
        <Box x={444} y={150} w={120} h={40} title="guideline_search" sub="hybrid pgvector" actor="rag" />
        <Box x={444} y={200} w={120} h={40} title="duplicate_check" sub="exact + semantic" actor="rag" />
        <Box x={576} y={150} w={110} h={40} title="coverage" sub="flash + cite" actor="flash" />
        <Box x={576} y={200} w={110} h={40} title="assess_narrative" sub="flash-lite" actor="lite" />
        <Box x={698} y={150} w={110} h={40} title="sanctions" sub="fail-closed" actor="det" />
        <Box x={698} y={200} w={110} h={40} title="fraud_scan" sub="rules + LLM" actor="det" />

        {/* ROUTER fan-out to workflows (row 3) */}
        {[
          { y: 320, t: "W1 · Straight-through", s: "auto-pay, tier-0 gate", term: "CLOSED", a: "det" as const },
          { y: 380, t: "W2 · Adjudication", s: "human approves", term: "SETTLED / DENIED", a: "human" as const },
          { y: 440, t: "W3 · Fraud (SIU)", s: "no payment edge", term: "ESCALATED", a: "human" as const },
          { y: 500, t: "W4 · Info request", s: "wait for documents", term: "INFO_PENDING", a: "det" as const },
          { y: 560, t: "W5 · High-severity", s: "senior adjuster", term: "ESCALATED", a: "human" as const },
        ].map((w, i) => (
          <g key={w.t}>
            <Edge x1={832} y1={88} x2={300 + 0} y2={w.y + 22} color="#334155" />
            <Box x={300} y={w.y} w={250} h={44} title={w.t} sub={w.s} actor={w.a} n={5 + i} />
            <Edge x1={550} y1={w.y + 22} x2={600} y2={w.y + 22} />
            <Box x={600} y={w.y} w={170} h={44} title={w.term} actor="term" />
          </g>
        ))}

        {/* settle/close detail under W1 */}
        <text x={300} y={312} fontSize="11" fontWeight="700" fill="#94a3b8">Router (rules R-00..R-99) → one of five typed workflows → terminal state</text>

        {/* legend */}
        <g>
          {[
            ["det", "Deterministic (orchestrator)"],
            ["lite", "LLM · flash-lite"],
            ["flash", "LLM · flash"],
            ["rag", "RAG (pgvector)"],
            ["human", "Human gate"],
            ["term", "Terminal state"],
          ].map(([k, label], i) => (
            <g key={k}>
              <rect x={830 + (i % 1) * 0} y={320 + i * 26} width={12} height={12} rx={3} fill={ACTOR_FILL[k]} />
              <text x={850} y={330 + i * 26} fontSize="11" fill="#cbd5e1">{label}</text>
            </g>
          ))}
        </g>
      </svg>
    </div>
  );
}
