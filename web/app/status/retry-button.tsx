"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";

export function RetryButton({ postId }: { postId: string }) {
  const router = useRouter();
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function retry() {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch("/api/retry", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ postId }),
      });
      if (!res.ok) {
        const body = (await res.json().catch(() => null)) as { error?: string } | null;
        throw new Error(body?.error ?? `Retry failed (${res.status})`);
      }
      router.refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Retry failed.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="shrink-0 text-right">
      <button
        onClick={retry}
        disabled={loading}
        className="rounded bg-zinc-900 px-3 py-1.5 text-sm text-white disabled:opacity-50 dark:bg-zinc-100 dark:text-zinc-900"
      >
        {loading ? "..." : "Retry"}
      </button>
      {error && <p className="mt-1 max-w-40 text-xs text-red-600">{error}</p>}
    </div>
  );
}
