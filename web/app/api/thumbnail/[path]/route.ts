import { NextResponse } from "next/server";

import { getSupabaseClient } from "@/lib/supabase";

// Short-lived: this route sits behind the app's auth middleware, but the
// signed URL it redirects to does not -- keeping the window small limits
// how long that URL would work if it ever leaked (browser history, a proxy
// log) after being issued to an authenticated request.
const SIGNED_URL_EXPIRY_S = 60;

// pipeline/media.py always writes storage paths as "<instagram_post_id>.jpg"
// -- Instagram shortcodes are alphanumeric plus - and _. Reject anything
// that doesn't match rather than passing an arbitrary string through to
// Supabase Storage.
const VALID_PATH = /^[A-Za-z0-9_-]+\.jpg$/;

export async function GET(
  _request: Request,
  { params }: { params: Promise<{ path: string }> },
) {
  // Next.js dynamic route segments arrive already URI-decoded.
  const { path } = await params;

  if (!VALID_PATH.test(path)) {
    return NextResponse.json({ error: "Invalid path." }, { status: 400 });
  }

  const bucket = process.env.SUPABASE_STORAGE_BUCKET;
  if (!bucket) {
    return NextResponse.json({ error: "Server misconfigured." }, { status: 500 });
  }

  const supabase = getSupabaseClient();
  const { data, error } = await supabase.storage
    .from(bucket)
    .createSignedUrl(path, SIGNED_URL_EXPIRY_S);

  if (error || !data) {
    return NextResponse.json({ error: "Thumbnail not found." }, { status: 404 });
  }

  return NextResponse.redirect(data.signedUrl);
}
