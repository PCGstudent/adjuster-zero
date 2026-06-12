"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { agent } from "./agent";
import { getSupabase } from "./supabase";
import type { Approval, Claim, ClaimDetail, GlobalEvent } from "./types";

/**
 * Live claims queue. Primary signal is Supabase Realtime on the `claims` table
 * (updates with no page refresh); a slow poll is a backstop for the no-DB local
 * mode and for resilience.
 */
export function useClaims(): { claims: Claim[]; refresh: () => void } {
  const [claims, setClaims] = useState<Claim[]>([]);
  const refresh = useCallback(() => {
    agent.claims().then(setClaims).catch(() => {});
  }, []);

  useEffect(() => {
    refresh();
    const poll = setInterval(refresh, 3000);
    const sb = getSupabase();
    const channel = sb
      ?.channel("claims-queue")
      .on("postgres_changes", { event: "*", schema: "public", table: "claims" }, refresh)
      .subscribe();
    return () => {
      clearInterval(poll);
      if (sb && channel) sb.removeChannel(channel);
    };
  }, [refresh]);

  return { claims, refresh };
}

/**
 * Live claim detail (the glass cockpit). Realtime on claim_events + tool_calls
 * for this claim triggers a refetch so the timeline grows without a refresh.
 */
export function useClaimDetail(id: string): ClaimDetail | null {
  const [detail, setDetail] = useState<ClaimDetail | null>(null);
  const idRef = useRef(id);
  idRef.current = id;

  const refresh = useCallback(() => {
    agent.claim(idRef.current).then(setDetail).catch(() => {});
  }, []);

  useEffect(() => {
    refresh();
    const poll = setInterval(refresh, 2000);
    const sb = getSupabase();
    const filter = `claim_id=eq.${id}`;
    const channel = sb
      ?.channel(`claim-${id}`)
      .on("postgres_changes", { event: "INSERT", schema: "public", table: "claim_events", filter }, refresh)
      .on("postgres_changes", { event: "INSERT", schema: "public", table: "tool_calls", filter }, refresh)
      .on("postgres_changes", { event: "*", schema: "public", table: "claims", filter: `id=eq.${id}` }, refresh)
      .subscribe();
    return () => {
      clearInterval(poll);
      if (sb && channel) sb.removeChannel(channel);
    };
  }, [id, refresh]);

  return detail;
}

/** Live approval inbox. Realtime on the approvals table + slow poll backstop. */
export function useApprovals(): { approvals: Approval[]; refresh: () => void } {
  const [approvals, setApprovals] = useState<Approval[]>([]);
  const refresh = useCallback(() => {
    agent.approvals().then(setApprovals).catch(() => {});
  }, []);

  useEffect(() => {
    refresh();
    const poll = setInterval(refresh, 3000);
    const sb = getSupabase();
    const channel = sb
      ?.channel("approvals-inbox")
      .on("postgres_changes", { event: "*", schema: "public", table: "approvals" }, refresh)
      .subscribe();
    return () => {
      clearInterval(poll);
      if (sb && channel) sb.removeChannel(channel);
    };
  }, [refresh]);

  return { approvals, refresh };
}

/** Global live event stream across all claims — the Agent Console. */
export function useGlobalEvents(): GlobalEvent[] {
  const [events, setEvents] = useState<GlobalEvent[]>([]);
  const refresh = useCallback(() => {
    agent.events().then(setEvents).catch(() => {});
  }, []);

  useEffect(() => {
    refresh();
    const poll = setInterval(refresh, 2500);
    const sb = getSupabase();
    const channel = sb
      ?.channel("agent-console")
      .on("postgres_changes", { event: "INSERT", schema: "public", table: "claim_events" }, refresh)
      .subscribe();
    return () => {
      clearInterval(poll);
      if (sb && channel) sb.removeChannel(channel);
    };
  }, [refresh]);

  return events;
}
