import { NextResponse } from "next/server";

import { envOr } from "@/lib/env";
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

  // Matches pipeline/config.py's default -- if SUPABASE_STORAGE_BUCKET is
  // left unset in .env, the pipeline uploads to "thumbnails" and this route
  // must resolve to the same bucket, not 500 on every image.
  const bucket = envOr("SUPABASE_STORAGE_BUCKET", "thumbnails");

  const supabase = getSupabaseClient();
  const { data, error } = await supabase.storage
    .from(bucket)
    .createSignedUrl(path, SIGNED_URL_EXPIRY_S);

  if (error || !data) {
    return NextResponse.json({ error: "Thumbnail not found." }, { status: 404 });
  }

  return NextResponse.redirect(data.signedUrl);
}
