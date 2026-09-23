import Link from "next/link";

import { getSupabaseClient } from "@/lib/supabase";
import type { CategoryCount, LibraryStats } from "@/lib/types";
import { SearchBox } from "./search-box";

// Live counts, not a build-time snapshot -- must render per request.
export const dynamic = "force-dynamic";

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

async function getCategoryCounts(): Promise<CategoryCount[]> {
  const supabase = getSupabaseClient();
  const { data, error } = await supabase.from("category_counts").select("*");
  if (error) throw new Error(`Failed to load category counts: ${error.message}`);
  return (data ?? []).map((row) => ({
    category: row.category as CategoryCount["category"],
    count: Number(row.count),
  }));
}

export default async function DashboardPage() {
  const [stats, categoryCounts] = await Promise.all([getStats(), getCategoryCounts()]);

  return (
    <main className="mx-auto max-w-2xl px-4 py-16">
      <h1 className="mb-2 text-center text-3xl font-semibold">Search your saves</h1>
      <p className="mb-8 text-center text-zinc-500">
        {stats.total} total · {stats.completed} processed · {stats.pending} pending ·{" "}
        {stats.processing} processing · {stats.failed} failed
      </p>

      <SearchBox />

      <div className="mt-10 flex justify-center">
        <Link
          href="/library"
          className="rounded-full bg-zinc-900 px-5 py-2 text-sm font-medium text-white hover:bg-zinc-700 dark:bg-zinc-100 dark:text-zinc-900 dark:hover:bg-zinc-300"
        >
          Browse library
        </Link>
      </div>

      {categoryCounts.length > 0 && (
        <div className="mt-6 flex flex-wrap justify-center gap-2">
          {categoryCounts.map(({ category, count }) => (
            <Link
              key={category}
              href={`/library?category=${encodeURIComponent(category)}`}
              className="rounded-full bg-zinc-100 px-3 py-1 text-sm text-zinc-700 hover:bg-zinc-200 dark:bg-zinc-800 dark:text-zinc-300 dark:hover:bg-zinc-700"
            >
              {category} · {count}
            </Link>
          ))}
        </div>
      )}

      {stats.failed > 0 && (
        <div className="mt-6 flex justify-center">
          <Link href="/status" className="text-sm text-red-600 hover:underline">
            {stats.failed} failed post{stats.failed === 1 ? "" : "s"}
          </Link>
        </div>
      )}
    </main>
  );
}
