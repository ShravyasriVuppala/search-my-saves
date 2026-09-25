"use client";

import { useRef, useState, type FormEvent } from "react";

import type { SearchResult } from "@/lib/types";

function thumbnailUrl(mediaStoragePath: string | null): string | null {
  if (!mediaStoragePath) return null;
  // Served through our own route (not a direct Supabase Storage URL) since
  // the bucket is private (plan.md D4/D5) -- see app/api/thumbnail/[path].
  return `/api/thumbnail/${encodeURIComponent(mediaStoragePath)}`;
}

export function SearchBox() {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<SearchResult[] | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Each search is tagged so a slow earlier response can't overwrite a
  // newer one. Every search costs a Gemini embedding call, so responses
  // take long enough that searching twice in quick succession really can
  // resolve out of order and leave the wrong results on screen.
  const latestRequest = useRef(0);

  // Only meaningful once there's something to clear -- otherwise it's a
  // permanently dead control sitting next to the primary action.
  const canClear = query.trim().length > 0 || results !== null;

  function clearSearch() {
    latestRequest.current += 1; // discard anything still in flight
    setQuery("");
    setResults(null);
    setError(null);
    setLoading(false);
  }

  async function runSearch(e: FormEvent) {
    e.preventDefault();
    const trimmed = query.trim();
    if (!trimmed) return;

    const requestId = ++latestRequest.current;
    setLoading(true);
    setError(null);
    try {
      const res = await fetch("/api/search", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ query: trimmed }),
      });
      if (!res.ok) {
        const body = (await res.json().catch(() => null)) as { error?: string } | null;
        throw new Error(body?.error ?? `Search failed (${res.status})`);
      }
      const data = (await res.json()) as { results: SearchResult[] };
      if (requestId !== latestRequest.current) return;
      setResults(data.results);
    } catch (err) {
      if (requestId !== latestRequest.current) return;
      setError(err instanceof Error ? err.message : "Search failed.");
      setResults(null);
    } finally {
      if (requestId === latestRequest.current) setLoading(false);
    }
  }

  return (
    <div>
      <form onSubmit={runSearch} className="mx-auto flex max-w-2xl gap-2">
        <input
          type="text"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="What do you remember about the post?"
          className="flex-1 rounded border border-zinc-300 px-4 py-3 text-lg dark:border-zinc-700 dark:bg-zinc-900"
        />
        <button
          type="submit"
          disabled={loading || !query.trim()}
          className="rounded bg-zinc-900 px-5 py-3 text-white disabled:opacity-50 dark:bg-zinc-100 dark:text-zinc-900"
        >
          {loading ? "..." : "Search"}
        </button>
        {canClear && (
          // type="button" so it doesn't submit the form and fire a search.
          <button
            type="button"
            onClick={clearSearch}
            disabled={loading}
            className="rounded border border-zinc-300 px-4 py-3 text-zinc-600 hover:bg-zinc-100 disabled:opacity-50 dark:border-zinc-700 dark:text-zinc-400 dark:hover:bg-zinc-800"
          >
            Clear
          </button>
        )}
      </form>

      {error && <p className="mt-4 text-sm text-red-600">{error}</p>}

      {results && results.length === 0 && <p className="mt-8 text-zinc-500">No results.</p>}

      {results && results.length > 0 && (
        <ul className="mt-8 grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-4">
          {results.map((r) => {
            const thumb = thumbnailUrl(r.media_storage_path);
            return (
              <li
                key={r.post_id}
                className="flex flex-col overflow-hidden rounded border border-zinc-200 dark:border-zinc-800"
              >
                {/* One link for the whole card rather than separate ones on
                    the image and title: same destination, so two would mean
                    two tab stops and two identical screen-reader
                    announcements. The disclosure below stays outside it,
                    since interactive content can't nest inside an anchor. */}
                <a href={`/post/${r.post_id}`} className="group flex flex-1 flex-col">
                  <div className="aspect-square bg-zinc-100 dark:bg-zinc-900">
                    {thumb ? (
                      // Served through our own signed route, so it isn't a
                      // static/optimizable asset next/image could handle.
                      // eslint-disable-next-line @next/next/no-img-element
                      <img
                        src={thumb}
                        alt={r.title ?? "Saved post thumbnail"}
                        loading="lazy"
                        className="h-full w-full object-cover transition group-hover:opacity-90"
                      />
                    ) : (
                      <div className="flex h-full items-center justify-center text-xs text-zinc-400">
                        no image
                      </div>
                    )}
                  </div>

                  <div className="flex flex-1 flex-col p-2">
                    <p
                      className="text-sm font-medium group-hover:underline"
                      title={r.title ?? undefined}
                    >
                      {r.title ?? "(untitled)"}
                    </p>
                    <p className="truncate text-xs text-zinc-500">
                      {r.category}
                      {r.subcategory ? ` · ${r.subcategory}` : ""}
                      {r.creator_username ? ` · @${r.creator_username}` : ""}
                    </p>
                    {r.summary && (
                      // Clamped so one long summary can't stretch every card
                      // in the row -- CSS grid sizes rows to the tallest item.
                      <p className="mt-1 line-clamp-3 text-xs text-zinc-600 dark:text-zinc-400">
                        {r.summary}
                      </p>
                    )}
                  </div>
                </a>

                <div className="px-2 pb-2">
                  {r.search_context && (
                    // Kept from the list view (plan.md §10): when a result looks
                    // wrong, this is what explains why it ranked. Collapsed by
                    // default so it doesn't break the grid's alignment.
                    <details className="text-xs text-zinc-500">
                      <summary className="cursor-pointer">why this matched</summary>
                      <p className="mt-1">{r.search_context}</p>
                    </details>
                  )}
                </div>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
