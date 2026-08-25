import { NextRequest, NextResponse } from "next/server";

import { SESSION_COOKIE_NAME, verifySessionToken } from "@/lib/auth";

// The entire auth story for this personal, single-user tool (plan.md §10):
// every route except /login and the keep-alive ping requires a valid signed
// session cookie. /api/keepalive is deliberately excluded -- it's hit by an
// unauthenticated GitHub Actions cron (plan.md D6) and does nothing beyond
// a trivial read, so gating it would just break the keep-alive without
// protecting anything meaningful.
export const config = {
  matcher: ["/((?!login|_next/static|_next/image|favicon.ico|api/keepalive).*)"],
};

export async function middleware(request: NextRequest) {
  const secret = process.env.APP_SESSION_SECRET;
  if (!secret) {
    // Fail closed: a misconfigured deployment must never silently serve the
    // app with no auth at all.
    return new NextResponse("Server misconfigured: APP_SESSION_SECRET is not set.", {
      status: 500,
    });
  }

  const token = request.cookies.get(SESSION_COOKIE_NAME)?.value;
  if (await verifySessionToken(token, secret)) {
    return NextResponse.next();
  }

  const loginUrl = new URL("/login", request.url);
  loginUrl.searchParams.set("next", request.nextUrl.pathname);
  return NextResponse.redirect(loginUrl);
}
