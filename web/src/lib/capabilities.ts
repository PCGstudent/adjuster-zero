// The nine agent capabilities and the event types that light each one up.
// One config file (blueprint Part 4 / showroom): the panel maps live events to
// capabilities so a viewer watches the agent demonstrate each one in real time.

export interface Capability {
  key: string;
  label: string;
  events: string[];
}

export const CAPABILITIES: Capability[] = [
  { key: "objective", label: "Receives an objective", events: ["claim.received"] },
  { key: "intent", label: "Understands intent", events: ["claim.extracted", "claim.classified"] },
  { key: "workflow", label: "Chooses a workflow", events: ["claim.routed"] },
  { key: "tools", label: "Selects tools", events: ["tool.completed", "claim.investigated"] },
  { key: "execute", label: "Executes", events: ["claim.executing", "claim.settled"] },
  { key: "state", label: "Maintains state", events: ["claim.routed", "approval.requested"] },
  { key: "uncertainty", label: "Handles uncertainty", events: ["agent.decision", "claim.investigated"] },
  { key: "escalate", label: "Escalates to a human", events: ["approval.requested", "claim.escalated", "claim.parked"] },
  { key: "outcome", label: "Produces measurable outcomes", events: ["claim.closed", "claim.denied", "claim.settled"] },
];

export function litCapabilities(eventTypes: Set<string>): Set<string> {
  const lit = new Set<string>();
  for (const cap of CAPABILITIES) {
    if (cap.events.some((e) => eventTypes.has(e))) lit.add(cap.key);
  }
  return lit;
}
