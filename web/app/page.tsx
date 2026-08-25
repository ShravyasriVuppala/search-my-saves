import Link from "next/link";

import { getSupabaseClient } from "@/lib/supabase";
import type { LibraryStats } from "@/lib/types";
import { SearchBox } from "./search-box";

async function getStats(): Promise<LibraryStats> {
  const supabase = getSupabaseClient();
  const { data, error } = await supabase.from("library_stats").select("*").single();
  if (error) throw new Error(`Failed to load stats: ${error.message}`);

  // library_stats' columns are count(*) (Postgres bigint); coerce explicitly
  // rather than assuming PostgREST serializes them as JSON numbers -- a
  // string "1" would make `stats.failed === 1` silently fail below.
  const row = data as Record<string, unknown>;
  return {
    total: Number(row.total),
    completed: Number(row.completed),
    processing: Number(row.processing),
    pending: Number(row.pending),
    failed: Number(row.failed),
  };
}

export default async function DashboardPage() {
  const stats = await getStats();

  return (
    <main className="mx-auto max-w-2xl px-4 py-16">
      <h1 className="mb-2 text-center text-3xl font-semibold">Search your saves</h1>
      <p className="mb-8 text-center text-zinc-500">
        {stats.total} total · {stats.completed} processed · {stats.processing} processing ·{" "}
        {stats.failed} failed
      </p>

      <SearchBox />

      <div className="mt-12 flex justify-center gap-6 text-sm">
        <Link href="/library" className="text-zinc-500 hover:underline">
          Browse library
        </Link>
        {stats.failed > 0 && (
          <Link href="/status" className="text-red-600 hover:underline">
            {stats.failed} failed post{stats.failed === 1 ? "" : "s"}
          </Link>
        )}
      </div>
    </main>
  );
}
