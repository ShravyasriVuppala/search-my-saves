import Link from "next/link";

import { getSupabaseClient } from "@/lib/supabase";
import { RetryButton } from "./retry-button";

interface FailedPost {
  id: string;
  instagram_post_id: string;
  instagram_url: string;
  creator_username: string | null;
  processing_error: string | null;
  retry_count: number;
  updated_at: string;
}

// Well above any realistic failure count for a personal library in normal
// operation -- a bound so this page can't silently truncate an unbounded
// list (the same class of bug found and fixed in media.py/reprocess.py's
// unpaginated selects), not a real pagination UI.
const MAX_FAILED_SHOWN = 500;

async function getFailedPosts(): Promise<{ posts: FailedPost[]; total: number }> {
  const supabase = getSupabaseClient();
  const { data, error, count } = await supabase
    .from("saved_posts")
    .select(
      "id, instagram_post_id, instagram_url, creator_username, processing_error, retry_count, updated_at",
      { count: "exact" },
    )
    .eq("processing_status", "FAILED")
    .order("updated_at", { ascending: false })
    .limit(MAX_FAILED_SHOWN);

  if (error) throw new Error(`Failed to load failed posts: ${error.message}`);
  return { posts: data ?? [], total: count ?? (data ?? []).length };
}

export default async function StatusPage() {
  const { posts, total } = await getFailedPosts();

  return (
    <main className="mx-auto max-w-3xl px-4 py-12">
      <div className="mb-6 flex items-center justify-between">
        <h1 className="text-2xl font-semibold">Failed posts</h1>
        <Link href="/" className="text-sm text-zinc-500 hover:underline">
          ← search
        </Link>
      </div>

      {total > posts.length && (
        <p className="mb-4 text-sm text-amber-600">
          Showing {posts.length} of {total} failed posts -- something is likely wrong with
          processing itself, worth investigating before retrying individually.
        </p>
      )}

      {posts.length === 0 ? (
        <p className="text-zinc-500">Nothing failed.</p>
      ) : (
        <ul className="space-y-4">
          {posts.map((post) => (
            <li
              key={post.id}
              className="flex items-start justify-between gap-4 rounded border border-zinc-200 p-4 dark:border-zinc-800"
            >
              <div className="min-w-0">
                <a
                  href={post.instagram_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="font-medium hover:underline"
                >
                  {post.instagram_post_id}
                </a>
                <p className="text-sm text-zinc-500">
                  {post.creator_username ? `@${post.creator_username} · ` : ""}
                  retried {post.retry_count}x
                </p>
                {post.processing_error && (
                  <p className="mt-1 break-words text-sm text-red-600">{post.processing_error}</p>
                )}
              </div>
              <RetryButton postId={post.id} />
            </li>
          ))}
        </ul>
      )}
    </main>
  );
}
