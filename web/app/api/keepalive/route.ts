import { NextResponse } from "next/server";

import { getSupabaseClient } from "@/lib/supabase";

// Hit by an unauthenticated weekly GitHub Actions cron
// (.github/workflows/keepalive.yml, plan.md D6) -- Supabase free-tier
// projects pause after 7 days with no API activity. Deliberately excluded
// from the auth middleware (see middleware.ts's matcher) and does nothing
// beyond a trivial read, so there's nothing here worth gating.
export async function GET() {
  try {
    const supabase = getSupabaseClient();
    const { error } = await supabase.from("library_stats").select("total").limit(1);
    if (error) throw error;
    return NextResponse.json({ ok: true });
  } catch (err) {
    console.error("keepalive failed:", err);
    return NextResponse.json({ ok: false }, { status: 500 });
  }
}
