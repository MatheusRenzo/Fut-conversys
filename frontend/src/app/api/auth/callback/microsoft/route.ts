import { NextRequest, NextResponse } from "next/server";
import { BACKEND_API_URL, setSessionCookie } from "@/lib/server-auth";

function appUrl(path: string) {
  const baseUrl = process.env.PUBLIC_APP_URL;
  return baseUrl ? new URL(path, baseUrl) : null;
}

export async function GET(request: NextRequest) {
  const code = request.nextUrl.searchParams.get("code");
  const error = request.nextUrl.searchParams.get("error");

  if (error || !code) {
    return NextResponse.redirect(appUrl(`/?error=${error || "microsoft_callback"}`) ?? new URL(`/?error=${error || "microsoft_callback"}`, request.url));
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
  return response;
}
