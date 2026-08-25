import { cookies } from "next/headers";
import { redirect } from "next/navigation";

import {
  createSessionToken,
  SESSION_COOKIE_NAME,
  SESSION_MAX_AGE_S,
  verifyPassword,
} from "@/lib/auth";

function safeNextPath(next: string | undefined): string {
  // Guards against an open redirect: `next` comes from a query param
  // (attacker-controllable), so only ever redirect to a relative in-app
  // path, never to an arbitrary external URL.
  return next && next.startsWith("/") && !next.startsWith("//") ? next : "/";
}

async function login(formData: FormData) {
  "use server";

  const password = String(formData.get("password") ?? "");
  const next = safeNextPath(String(formData.get("next") ?? ""));

  const expected = process.env.APP_PASSWORD;
  const secret = process.env.APP_SESSION_SECRET;
  if (!expected || !secret) {
    throw new Error("Server misconfigured: APP_PASSWORD / APP_SESSION_SECRET not set.");
  }

  const ok = await verifyPassword(password, expected, secret);
  if (!ok) {
    redirect(`/login?error=1&next=${encodeURIComponent(next)}`);
  }

  const token = await createSessionToken(secret);
  const cookieStore = await cookies();
  cookieStore.set(SESSION_COOKIE_NAME, token, {
    httpOnly: true,
    secure: process.env.NODE_ENV === "production",
    sameSite: "lax",
    maxAge: SESSION_MAX_AGE_S,
    path: "/",
  });

  redirect(next);
}

export default async function LoginPage({
  searchParams,
}: {
  searchParams: Promise<{ error?: string; next?: string }>;
}) {
  const params = await searchParams;
  const next = safeNextPath(params.next);

  return (
    <main className="flex min-h-screen items-center justify-center px-4">
      <form action={login} className="w-full max-w-sm space-y-4">
        <h1 className="text-center text-xl font-semibold">Search My Saves</h1>
        <input type="hidden" name="next" value={next} />
        <input
          type="password"
          name="password"
          placeholder="Password"
          autoFocus
          required
          className="w-full rounded border border-zinc-300 px-3 py-2 dark:border-zinc-700 dark:bg-zinc-900"
        />
        {params.error && <p className="text-sm text-red-600">Incorrect password.</p>}
        <button
          type="submit"
          className="w-full rounded bg-zinc-900 px-3 py-2 text-white hover:bg-zinc-700 dark:bg-zinc-100 dark:text-zinc-900"
        >
          Enter
        </button>
      </form>
    </main>
  );
}
