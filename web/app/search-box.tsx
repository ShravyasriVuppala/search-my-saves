"use client";

import { useState, type FormEvent } from "react";

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

  // Only meaningful once there's something to clear -- otherwise it's a
  // permanently dead control sitting next to the primary action.
  const canClear = query.trim().length > 0 || results !== null;

  function clearSearch() {
    setQuery("");
    setResults(null);
    setError(null);
  }

  async function runSearch(e: FormEvent) {
    e.preventDefault();
    const trimmed = query.trim();
    if (!trimmed) return;

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
      setResults(data.results);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Search failed.");
      setResults(null);
    } finally {
      setLoading(false);
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
                <a href={`/post/${r.post_id}`} className="group">
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
                </a>

                <div className="flex flex-1 flex-col p-2">
                  <a
                    href={`/post/${r.post_id}`}
                    className="text-sm font-medium hover:underline"
                    title={r.title ?? undefined}
                  >
                    {r.title ?? "(untitled)"}
                  </a>
                  <p className="truncate text-xs text-zinc-500">
                    {r.category}
                    {r.subcategory ? ` · ${r.subcategory}` : ""}
                    {r.creator_username ? ` · @${r.creator_username}` : ""}
                  </p>
                  {r.summary && <p className="mt-1 text-xs text-zinc-600 dark:text-zinc-400">{r.summary}</p>}
                  {r.search_context && (
                    // Kept from the list view (plan.md §10): when a result looks
                    // wrong, this is what explains why it ranked. Collapsed by
                    // default so it doesn't break the grid's alignment.
                    <details className="mt-auto pt-2 text-xs text-zinc-500">
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
