"use client";

import { useState, type FormEvent } from "react";

import type { SearchResult } from "@/lib/types";

export function SearchBox() {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<SearchResult[] | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

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
      <form onSubmit={runSearch} className="flex gap-2">
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
      </form>

      {error && <p className="mt-4 text-sm text-red-600">{error}</p>}

      {results && (
        <ul className="mt-8 space-y-4">
          {results.length === 0 && <li className="text-zinc-500">No results.</li>}
          {results.map((r) => (
            <li key={r.post_id} className="rounded border border-zinc-200 p-4 dark:border-zinc-800">
              <a href={`/post/${r.post_id}`} className="font-medium hover:underline">
                {r.title ?? "(untitled)"}
              </a>
              <p className="text-sm text-zinc-500">
                {r.category}
                {r.subcategory ? ` · ${r.subcategory}` : ""}
                {r.creator_username ? ` · @${r.creator_username}` : ""}
              </p>
              {r.summary && <p className="mt-1 text-sm">{r.summary}</p>}
              {r.search_context && (
                <details className="mt-1 text-sm text-zinc-500">
                  <summary className="cursor-pointer">why this matched</summary>
                  <p className="mt-1">{r.search_context}</p>
                </details>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
