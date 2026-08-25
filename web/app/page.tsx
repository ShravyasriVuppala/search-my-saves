import Link from "next/link";

import { getSupabaseClient } from "@/lib/supabase";
import type { LibraryStats } from "@/lib/types";
import { SearchBox } from "./search-box";

async function getStats(): Promise<LibraryStats> {
  const supabase = getSupabaseClient();
  const { data, error } = await supabase.from("library_stats").select("*").single();
  if (error) throw new Error(`Failed to load stats: ${error.message}`);
  return data as LibraryStats;
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
