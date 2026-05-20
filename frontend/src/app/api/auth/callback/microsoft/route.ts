import { NextRequest, NextResponse } from "next/server";
import { BACKEND_API_URL, setSessionCookie } from "@/lib/server-auth";

export async function GET(request: NextRequest) {
  const code = request.nextUrl.searchParams.get("code");
  const error = request.nextUrl.searchParams.get("error");

  if (error || !code) {
    return NextResponse.redirect(new URL(`/?error=${error || "microsoft_callback"}`, request.url));
  }

  const redirectUri = new URL("/api/auth/callback/microsoft", request.url).toString();
  const backendResponse = await fetch(`${BACKEND_API_URL}/api/auth/microsoft/callback`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ code, redirect_uri: redirectUri }),
  });

  if (!backendResponse.ok) {
    return NextResponse.redirect(new URL("/?error=microsoft_login", request.url));
  }

  const data = await backendResponse.json();
  const response = NextResponse.redirect(new URL("/dashboard", request.url));
  setSessionCookie(response, data.token);
  return response;
}
