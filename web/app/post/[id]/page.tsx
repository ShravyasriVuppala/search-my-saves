import Link from "next/link";
import { notFound } from "next/navigation";

import { getSupabaseClient } from "@/lib/supabase";
import type { Category } from "@/lib/types";

interface PostDetail {
  id: string;
  instagram_url: string;
  creator_username: string | null;
  caption: string | null;
  media_type: string | null;
  media_storage_path: string | null;
  saved_at: string | null;
  posted_at: string | null;
  processing_status: string;
  // No !inner here (unlike the library page) -- a post that's still
  // PENDING/PROCESSING/FAILED has no content_analysis row yet, and this
  // page should still render for it, just with the AI fields empty.
  content_analysis: {
    title: string | null;
    category: Category | null;
    subcategory: string | null;
    summary: string | null;
    search_context: string | null;
    keywords: string[];
    entities: string[];
    ai_metadata: Record<string, unknown>;
  } | null;
}

async function getPost(id: string): Promise<PostDetail | null> {
  const supabase = getSupabaseClient();
  const { data, error } = await supabase
    .from("saved_posts")
    .select(
      "id, instagram_url, creator_username, caption, media_type, media_storage_path, " +
        "saved_at, posted_at, processing_status, content_analysis(title, category, " +
        "subcategory, summary, search_context, keywords, entities, ai_metadata)",
    )
    .eq("id", id)
    .maybeSingle();

  if (error) throw new Error(`Failed to load post: ${error.message}`);
  return data as unknown as PostDetail | null;
}

function formatMetadataKey(key: string): string {
  return key.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

function formatMetadataValue(value: unknown): string {
  if (Array.isArray(value)) return value.join(", ");
  if (value === null || value === undefined) return "";
  // ai_metadata is genuinely schema-less (CLAUDE.md principle 5); a nested
  // object is unexpected but possible, and String() on one just prints
  // "[object Object]" -- JSON.stringify at least stays readable.
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

export default async function PostDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const post = await getPost(id);
  if (!post) notFound();

  const analysis = post.content_analysis;
  const thumb = post.media_storage_path
    ? `/api/thumbnail/${encodeURIComponent(post.media_storage_path)}`
    : null;
  const metadataEntries = Object.entries(analysis?.ai_metadata ?? {}).filter(
    ([, v]) => v !== null && v !== undefined && v !== "",
  );

  return (
    <main className="mx-auto max-w-3xl px-4 py-12">
      <Link href="/library" className="text-sm text-zinc-500 hover:underline">
        ← library
      </Link>

      <div className="mt-4 grid gap-8 sm:grid-cols-2">
        <div className="aspect-square overflow-hidden rounded bg-zinc-100 dark:bg-zinc-900">
          {thumb ? (
            // eslint-disable-next-line @next/next/no-img-element -- served
            // through our own signed route, not a static/optimizable asset
            <img
              src={thumb}
              alt={analysis?.title ?? "Saved post"}
              className="h-full w-full object-cover"
            />
          ) : (
            <div className="flex h-full items-center justify-center text-sm text-zinc-400">
              no image
            </div>
          )}
        </div>

        <div>
          <h1 className="text-2xl font-semibold">{analysis?.title ?? "(untitled)"}</h1>
          <p className="mt-1 text-sm text-zinc-500">
            {analysis ? (
              <>
                {analysis.category}
                {analysis.subcategory ? ` · ${analysis.subcategory}` : ""}
              </>
            ) : (
              `status: ${post.processing_status}`
            )}
          </p>

          {analysis?.summary && <p className="mt-4">{analysis.summary}</p>}

          {analysis?.search_context && (
            <p className="mt-2 text-sm text-zinc-500">{analysis.search_context}</p>
          )}

          {analysis && analysis.keywords.length > 0 && (
            <div className="mt-4 flex flex-wrap gap-1">
              {analysis.keywords.map((k) => (
                <span
                  key={k}
                  className="rounded-full bg-zinc-100 px-2 py-0.5 text-xs text-zinc-600 dark:bg-zinc-800 dark:text-zinc-300"
                >
                  {k}
                </span>
              ))}
            </div>
          )}

          {metadataEntries.length > 0 && (
            <dl className="mt-6 space-y-1 text-sm">
              {metadataEntries.map(([key, value]) => (
                <div key={key} className="flex justify-between gap-4">
                  <dt className="text-zinc-500">{formatMetadataKey(key)}</dt>
                  <dd className="text-right">{formatMetadataValue(value)}</dd>
                </div>
              ))}
            </dl>
          )}

          {!analysis && post.caption && (
            <p className="mt-4 whitespace-pre-line text-sm text-zinc-500">{post.caption}</p>
          )}

          <div className="mt-8 flex items-center justify-between text-sm">
            <span className="text-zinc-500">
              {post.creator_username ? `@${post.creator_username}` : ""}
              {post.saved_at ? ` · saved ${new Date(post.saved_at).toLocaleDateString()}` : ""}
            </span>
            <a
              href={post.instagram_url}
              target="_blank"
              rel="noopener noreferrer"
              className="text-zinc-900 hover:underline dark:text-zinc-100"
            >
              View on Instagram →
            </a>
          </div>
        </div>
      </div>
    </main>
  );
}
