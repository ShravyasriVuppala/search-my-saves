import "server-only";
import { createClient, type SupabaseClient } from "@supabase/supabase-js";

// `server-only` makes any accidental import of this module from client
// component code a build-time error, not a runtime leak -- the whole point
// of plan.md D5: the browser never talks to Supabase, and the service-role
// key must never reach a client bundle.

let client: SupabaseClient | null = null;

export function getSupabaseClient(): SupabaseClient {
  if (client) return client;

  const url = process.env.SUPABASE_URL;
  const key = process.env.SUPABASE_SERVICE_ROLE_KEY;
  if (!url || !key) {
    throw new Error("SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY are not set.");
  }

  client = createClient(url, key, {
    // No end-user auth session to persist -- this app's own password gate
    // (lib/auth.ts) is entirely separate from Supabase Auth, and there's no
    // browser storage to persist to on the server anyway.
    auth: { persistSession: false },
  });
  return client;
}
