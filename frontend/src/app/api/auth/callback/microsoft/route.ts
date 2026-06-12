import { NextRequest, NextResponse } from "next/server";
import { BACKEND_API_URL, setSessionCookie } from "@/lib/server-auth";

const OAUTH_STATE_COOKIE = "ms_oauth_state";

function appUrl(path: string) {
  const baseUrl = process.env.PUBLIC_APP_URL;
  return baseUrl ? new URL(path, baseUrl) : null;
}

export async function GET(request: NextRequest) {
  const code = request.nextUrl.searchParams.get("code");
  const error = request.nextUrl.searchParams.get("error");
  const state = request.nextUrl.searchParams.get("state");
  const expectedState = request.cookies.get(OAUTH_STATE_COOKIE)?.value;

  if (error || !code) {
    return NextResponse.redirect(appUrl(`/?error=${error || "microsoft_callback"}`) ?? new URL(`/?error=${error || "microsoft_callback"}`, request.url));
  }

  // Anti-CSRF: o state da query precisa existir e bater com o cookie da sessão.
  if (!state || !expectedState || state !== expectedState) {
    const url = appUrl("/") ?? new URL("/", request.url);
    url.searchParams.set("error", "invalid_state");
    const res = NextResponse.redirect(url);
    res.cookies.set(OAUTH_STATE_COOKIE, "", { path: "/", maxAge: 0 });
    return res;
  }

  const redirectUri = process.env.MICROSOFT_REDIRECT_URI ?? new URL("/api/auth/callback/microsoft", request.url).toString();
  const backendResponse = await fetch(`${BACKEND_API_URL}/api/auth/microsoft/callback`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ code, redirect_uri: redirectUri }),
  });

  if (!backendResponse.ok) {
    const errorData = await backendResponse.json().catch(() => null);
    const isDomainBlocked =
      backendResponse.status === 403 && errorData?.detail === "domain_not_allowed";
    console.error("Microsoft login failed", backendResponse.status);
    const redirectUrl = appUrl("/") ?? new URL("/", request.url);
    redirectUrl.searchParams.set("error", isDomainBlocked ? "domain_not_allowed" : "microsoft_login");
    return NextResponse.redirect(redirectUrl);
  }

  const data = await backendResponse.json();
  const response = NextResponse.redirect(appUrl("/dashboard") ?? new URL("/dashboard", request.url));
  setSessionCookie(response, data.token);
  response.cookies.set(OAUTH_STATE_COOKIE, "", { path: "/", maxAge: 0 });
  return response;
}
