export interface Claim {
  id: string;
  state: string;
  workflow: string | null;
  line: string | null;
  peril: string | null;
  severity: number | null;
  fraud_score: number | null;
  confidence: number | null;
  completeness: number | null;
  amount_est: number | null;
  reserve: number | null;
  paid: number | null;
  claimant_id: string | null;
  policy_id: string | null;
  updated_at: string;
}

export interface ClaimEvent {
  id: number;
  ts: string;
  type: string;
  actor: { kind?: string; component?: string };
  data: Record<string, unknown>;
  trace_id: string | null;
}

export interface ToolCall {
  id: number;
  ts: string;
  tool: string;
  risk_tier: number;
  args: Record<string, unknown> | null;
  result: Record<string, unknown> | null;
  status: string;
  error_code: string | null;
  latency_ms: number | null;
  cached: boolean;
}

export interface AgentDecision {
  id: number;
  ts: string;
  decision_type: string;
  model: string | null;
  output: Record<string, unknown> | null;
  confidence: number | null;
  alternatives: unknown[] | null;
  citations: unknown[] | null;
  rule_id: string | null;
  tokens_in: number | null;
  tokens_out: number | null;
  latency_ms: number | null;
}

export interface ClaimDetail {
  claim: Claim;
  events: ClaimEvent[];
  decisions: AgentDecision[];
  tool_calls: ToolCall[];
}

export interface Scenario {
  key: string;
  title: string;
  expected_route: string | null;
}

export interface GlobalEvent {
  id: number;
  claim_id: string;
  ts: string;
  type: string;
  actor: { kind?: string; component?: string };
  data: Record<string, unknown>;
}

export interface JourneyStep {
  index: number;
  phase: string;
  actor: string;
  title: string;
  subtitle: string;
  input: { label: string; value: unknown };
  output: { label: string; value: unknown };
  explanation: string;
  meta: Record<string, unknown>;
  prompt: { system: string | null; user: string | null } | null;
}

export interface Journey {
  claim_id: string;
  final: {
    state: string | null;
    workflow: string | null;
    rule_id: string | null;
    paid: number | null;
    amount_est: number | null;
    fraud_score: number | null;
  };
  phases: { key: string; label: string; active: boolean }[];
  steps: JourneyStep[];
}

export interface Approval {
  id: string;
  claim_id: string;
  requested_action: {
    type: string;
    amount?: number;
    reason?: string;
    payee_id?: string;
  };
  risk_tier: number;
  confidence: number | null;
  status: string;
  created_at: string;
  sla_at: string | null;
}
