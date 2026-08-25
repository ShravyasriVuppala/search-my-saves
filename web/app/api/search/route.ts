import { NextRequest, NextResponse } from "next/server";

import { search } from "@/lib/search";
import type { Category } from "@/lib/types";

interface SearchRequestBody {
  query?: string;
  category?: Category | null;
  limit?: number;
}

export async function POST(request: NextRequest) {
  let body: SearchRequestBody;
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ error: "Invalid JSON body." }, { status: 400 });
  }

  const query = (body.query ?? "").trim();
  if (!query) {
    return NextResponse.json({ error: "query is required." }, { status: 400 });
  }

  const limit = Math.min(Math.max(body.limit ?? 10, 1), 50);

  try {
    const results = await search(query, { limit, category: body.category ?? null });
    return NextResponse.json({ results });
  } catch (err) {
    // Log the real error server-side; never forward internal error details
    // (DB messages, stack traces) to the client.
    console.error("search failed:", err);
    return NextResponse.json({ error: "Search failed." }, { status: 500 });
  }
}
