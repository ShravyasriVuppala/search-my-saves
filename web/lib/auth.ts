/**
 * The entire auth system (plan.md §10): one password, one signed session
 * cookie. Built on the Web Crypto API rather than Node's `crypto` module so
 * it works identically in the Edge middleware and in Server Actions/Route
 * Handlers (which may run on either runtime).
 */

const SESSION_MAX_AGE_S = 60 * 60 * 24 * 90; // 90 days
const SESSION_COOKIE_NAME = "sms_session";

function base64UrlEncode(bytes: Uint8Array): string {
  let binary = "";
  for (const b of bytes) binary += String.fromCharCode(b);
  return btoa(binary).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

function base64UrlDecode(str: string): Uint8Array {
  const padded = str.replace(/-/g, "+").replace(/_/g, "/").padEnd(str.length + ((4 - (str.length % 4)) % 4), "=");
  const binary = atob(padded);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
  return bytes;
}

async function hmacSha256(key: string, message: string): Promise<Uint8Array> {
  const enc = new TextEncoder();
  const cryptoKey = await crypto.subtle.importKey(
    "raw",
    enc.encode(key) as BufferSource,
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["sign"],
  );
  const sig = await crypto.subtle.sign("HMAC", cryptoKey, enc.encode(message) as BufferSource);
  return new Uint8Array(sig);
}

function constantTimeEqual(a: Uint8Array, b: Uint8Array): boolean {
  // Both inputs here are always fixed-length HMAC-SHA256 digests (32 bytes),
  // so a length check up front doesn't leak anything input-dependent.
  if (a.length !== b.length) return false;
  let diff = 0;
  for (let i = 0; i < a.length; i++) diff |= a[i] ^ b[i];
  return diff === 0;
}

/** Compares the submitted password to APP_PASSWORD without leaking timing
 * information through early-exit string comparison. Hashing both sides
 * first also means the comparison is over a fixed 32-byte digest regardless
 * of password length, so length itself isn't observable either. */
export async function verifyPassword(
  submitted: string,
  expected: string,
  secret: string,
): Promise<boolean> {
  const [a, b] = await Promise.all([hmacSha256(secret, submitted), hmacSha256(secret, expected)]);
  return constantTimeEqual(a, b);
}

export async function createSessionToken(secret: string): Promise<string> {
  const exp = Date.now() + SESSION_MAX_AGE_S * 1000;
  const payload = base64UrlEncode(new TextEncoder().encode(JSON.stringify({ exp })));
  const sig = base64UrlEncode(await hmacSha256(secret, payload));
  return `${payload}.${sig}`;
}

export async function verifySessionToken(
  token: string | undefined,
  secret: string,
): Promise<boolean> {
  if (!token) return false;
  const parts = token.split(".");
  if (parts.length !== 2) return false;
  const [payload, sig] = parts;

  // Everything below parses untrusted cookie content -- base64UrlDecode's
  // atob() throws DOMException on malformed input, which a corrupted or
  // tampered cookie value can trivially trigger. Without this try/catch
  // wrapping the whole thing (not just the JSON.parse), that throw would
  // propagate out of this function as an unhandled rejection; middleware.ts
  // awaits this directly with no catch of its own, so a bad cookie would
  // 500 the request instead of failing safely to "not authenticated".
  try {
    const expectedSig = await hmacSha256(secret, payload);
    if (!constantTimeEqual(base64UrlDecode(sig), expectedSig)) return false;

    const { exp } = JSON.parse(new TextDecoder().decode(base64UrlDecode(payload))) as {
      exp: number;
    };
    return typeof exp === "number" && Date.now() < exp;
  } catch {
    return false;
  }
}

export { SESSION_COOKIE_NAME, SESSION_MAX_AGE_S };
