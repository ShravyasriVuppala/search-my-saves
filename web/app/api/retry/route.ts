import { NextRequest, NextResponse } from "next/server";

import { getSupabaseClient } from "@/lib/supabase";

interface RetryRequestBody {
  postId?: string;
}

// saved_posts.id is a uuid column -- validating here gives a clear 400
// instead of the request falling through to Postgres's own type-cast
// error, which the code below still handles (as a 500), just less clearly.
const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

export async function POST(request: NextRequest) {
  let body: RetryRequestBody;
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ error: "Invalid JSON body." }, { status: 400 });
  }

  const postId = body.postId;
  if (!postId || typeof postId !== "string" || !UUID_RE.test(postId)) {
    return NextResponse.json({ error: "postId is required and must be a valid UUID." }, { status: 400 });
  }

  const supabase = getSupabaseClient();

  // Scoped to processing_status="FAILED" so this can't be (ab)used to
  // interrupt a post that's currently PROCESSING or reset one that's
  // already COMPLETED -- only a genuinely failed post can be requeued.
  const { data, error } = await supabase
    .from("saved_posts")
    .update({ processing_status: "PENDING", retry_count: 0, processing_error: null })
    .eq("id", postId)
    .eq("processing_status", "FAILED")
    .select("id");

  if (error) {
    console.error("retry failed:", error);
    return NextResponse.json({ error: "Retry failed." }, { status: 500 });
  }
  if (!data || data.length === 0) {
    return NextResponse.json(
      { error: "Post not found or not in FAILED state." },
      { status: 404 },
    );
  }

  return NextResponse.json({ ok: true });
}
