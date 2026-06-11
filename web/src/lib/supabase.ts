import { createClient, type SupabaseClient } from "@supabase/supabase-js";

const url = process.env.NEXT_PUBLIC_SUPABASE_URL;
const anon = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;

/**
 * Browser Supabase client (anon key → governed by RLS: read-only viewer access).
 * Returns null when env is unconfigured so the UI can show "not connected"
 * instead of crashing at build/render time.
 */
export function getSupabase(): SupabaseClient | null {
  if (!url || !anon) return null;
  return createClient(url, anon, {
    realtime: { params: { eventsPerSecond: 10 } },
  });
}

export const supabaseConfigured = Boolean(url && anon);
