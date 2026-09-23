import Link from "next/link";

import { getSupabaseClient } from "@/lib/supabase";
import { CATEGORIES, type Category } from "@/lib/types";

// Live library contents, not a build-time snapshot -- must render per request.
export const dynamic = "force-dynamic";

const PAGE_SIZE = 48;

interface LibraryRow {
  id: string;
  instagram_url: string;
  creator_username: string | null;
  media_storage_path: string | null;
  saved_at: string | null;
  // One-to-one: content_analysis.post_id is both its FK to saved_posts and
  // its own primary key, so PostgREST returns this as a single object, not
  // an array, for the `!inner` embed below.
  content_analysis: {
    title: string | null;
    category: Category | null;
    subcategory: string | null;
    keywords: string[];
  } | null;
}

async function getPosts(page: number, category: Category | null) {
  const supabase = getSupabaseClient();
  const from = page * PAGE_SIZE;
  const to = from + PAGE_SIZE - 1;

  // !inner on content_analysis does two things at once: only shows posts
  // that have actually been analyzed (COMPLETED), and makes filtering on
  // content_analysis.category reliable -- PostgREST's embedded-resource
  // filtering is only well-defined for inner joins.
  let query = supabase
    .from("saved_posts")
    .select(
      "id, instagram_url, creator_username, media_storage_path, saved_at, " +
        "content_analysis!inner(title, category, subcategory, keywords)",
      { count: "exact" },
    )
    .order("saved_at", { ascending: false, nullsFirst: false })
    .range(from, to);

  if (category) {
    query = query.eq("content_analysis.category", category);
  }

  const { data, error, count } = await query;
  if (error) throw new Error(`Failed to load library: ${error.message}`);
  return { posts: (data ?? []) as unknown as LibraryRow[], total: count ?? 0 };
}

function thumbnailUrl(mediaStoragePath: string | null): string | null {
  if (!mediaStoragePath) return null;
  // Served through our own route (not a direct Supabase Storage URL) since
  // the bucket is private (plan.md D4/D5) -- see app/api/thumbnail/[path].
  return `/api/thumbnail/${encodeURIComponent(mediaStoragePath)}`;
}

export default async function LibraryPage({
  searchParams,
}: {
  searchParams: Promise<{ page?: string; category?: string }>;
}) {
  const params = await searchParams;
  const page = Math.max(0, Number(params.page ?? "0") || 0);
  const category = CATEGORIES.includes(params.category as Category)
    ? (params.category as Category)
    : null;

  const { posts, total } = await getPosts(page, category);
  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));

  function pageHref(p: number, cat: Category | null) {
    const qs = new URLSearchParams();
    if (p > 0) qs.set("page", String(p));
    if (cat) qs.set("category", cat);
    const s = qs.toString();
    return s ? `/library?${s}` : "/library";
  }

  return (
    <main className="mx-auto max-w-6xl px-4 py-12">
      <div className="mb-6 flex items-center justify-between">
        <h1 className="text-2xl font-semibold">Library</h1>
        <Link href="/" className="text-sm text-zinc-500 hover:underline">
          ← search
        </Link>
      </div>

      <div className="mb-8 flex flex-wrap gap-2">
        <Link
          href={pageHref(0, null)}
          className={`rounded-full px-3 py-1 text-sm ${
            category === null
              ? "bg-zinc-900 text-white dark:bg-zinc-100 dark:text-zinc-900"
              : "bg-zinc-100 text-zinc-700 dark:bg-zinc-800 dark:text-zinc-300"
          }`}
        >
          All
        </Link>
        {CATEGORIES.map((c) => (
          <Link
            key={c}
            href={pageHref(0, c)}
            className={`rounded-full px-3 py-1 text-sm ${
              category === c
                ? "bg-zinc-900 text-white dark:bg-zinc-100 dark:text-zinc-900"
                : "bg-zinc-100 text-zinc-700 dark:bg-zinc-800 dark:text-zinc-300"
            }`}
          >
            {c}
          </Link>
        ))}
      </div>

      {posts.length === 0 ? (
        <p className="text-zinc-500">No posts yet.</p>
      ) : (
        <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-6">
          {posts.map((post) => {
            const analysis = post.content_analysis;
            const thumb = thumbnailUrl(post.media_storage_path);
            return (
              <Link
                key={post.id}
                href={`/post/${post.id}`}
                className="group overflow-hidden rounded border border-zinc-200 dark:border-zinc-800"
              >
                <div className="aspect-square bg-zinc-100 dark:bg-zinc-900">
                  {thumb ? (
                    // eslint-disable-next-line @next/next/no-img-element -- served
                    // through our own signed route, not a static/optimizable asset
                    <img
                      src={thumb}
                      alt={analysis?.title ?? "Saved post thumbnail"}
                      className="h-full w-full object-cover transition group-hover:opacity-90"
                    />
                  ) : (
                    <div className="flex h-full items-center justify-center text-xs text-zinc-400">
                      no image
                    </div>
                  )}
                </div>
                <div className="p-2">
                  <p className="truncate text-sm font-medium">{analysis?.title ?? "(untitled)"}</p>
                  <p className="truncate text-xs text-zinc-500">
                    {analysis?.category}
                    {analysis?.subcategory ? ` · ${analysis.subcategory}` : ""}
                  </p>
                </div>
              </Link>
            );
          })}
        </div>
      )}

      {totalPages > 1 && (
        <div className="mt-8 flex items-center justify-center gap-4 text-sm">
          <Link
            href={pageHref(Math.max(0, page - 1), category)}
            aria-disabled={page === 0}
            className={page === 0 ? "pointer-events-none text-zinc-300" : "hover:underline"}
          >
            ← prev
          </Link>
          <span className="text-zinc-500">
            page {page + 1} of {totalPages}
          </span>
          <Link
            href={pageHref(Math.min(totalPages - 1, page + 1), category)}
            aria-disabled={page >= totalPages - 1}
            className={
              page >= totalPages - 1 ? "pointer-events-none text-zinc-300" : "hover:underline"
            }
          >
            next →
          </Link>
        </div>
      )}
    </main>
  );
}
