import { NextRequest, NextResponse } from "next/server";
import { BACKEND_API_URL } from "@/lib/server-auth";

// Inicia o login Microsoft gerando um `state` anti-CSRF, guardando-o num cookie
// httpOnly de mesma origem e buscando no backend a URL de autorização (com esse
// state). O navegador é redirecionado direto à Microsoft; o callback compara o
// state da query com o do cookie antes de aceitar o login.
export const OAUTH_STATE_COOKIE = "ms_oauth_state";

export async function GET(_request: NextRequest) {
  const state = crypto.randomUUID().replace(/-/g, "") + crypto.randomUUID().replace(/-/g, "");

  // O backend responde 302 com Location = URL de autorização da Microsoft.
  const backendResponse = await fetch(
    `${BACKEND_API_URL}/api/auth/microsoft/start?state=${state}`,
    { redirect: "manual" },
  );
  const authorizeUrl = backendResponse.headers.get("location");
  if (!authorizeUrl || !authorizeUrl.startsWith("https://login.microsoftonline.com/")) {
    return NextResponse.redirect(new URL("/?error=microsoft_unavailable", _request.url));
  }

  const response = NextResponse.redirect(authorizeUrl);
  response.cookies.set(OAUTH_STATE_COOKIE, state, {
    httpOnly: true,
    sameSite: "lax",
    secure: process.env.NODE_ENV === "production",
    path: "/",
    maxAge: 600,
  });
  return response;
}
