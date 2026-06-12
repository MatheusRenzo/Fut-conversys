import { NextRequest, NextResponse } from "next/server";
import { BACKEND_API_URL, clearSessionCookie, getSessionToken } from "@/lib/server-auth";

const PUBLIC_BACKEND_PATHS = new Set([
  "api/auth/microsoft/config",
  "api/auth/microsoft/start",
  "api/health",
]);

// Avatares e banners são públicos e cacheáveis pelo navegador
const PUBLIC_BACKEND_PATTERNS = [/^api\/users\/\d+\/(?:avatar|banner)$/];

async function proxy(request: NextRequest, { params }: { params: Promise<{ path: string[] }> }) {
  const { path } = await params;
  const backendPath = path.join("/");
  const isPublic =
    PUBLIC_BACKEND_PATHS.has(backendPath) || PUBLIC_BACKEND_PATTERNS.some((pattern) => pattern.test(backendPath));
  const token = await getSessionToken();

  if (!isPublic && !token) {
    return NextResponse.json({ detail: "Sessão expirada" }, { status: 401 });
  }

  const target = new URL(`/${backendPath}${request.nextUrl.search}`, BACKEND_API_URL);
  const headers = new Headers();
  const contentType = request.headers.get("content-type");
  if (contentType) headers.set("Content-Type", contentType);
  const ifNoneMatch = request.headers.get("if-none-match");
  if (ifNoneMatch) headers.set("If-None-Match", ifNoneMatch);
  if (token) headers.set("Authorization", `Bearer ${token}`);

  const backendResponse = await fetch(target, {
    method: request.method,
    headers,
    body: ["GET", "HEAD"].includes(request.method) ? undefined : await request.text(),
    redirect: "manual",
  });

  if (backendResponse.status >= 300 && backendResponse.status < 400 && backendResponse.status !== 304) {
    const location = backendResponse.headers.get("location");
    if (location) return NextResponse.redirect(location);
  }

  // arrayBuffer preserva respostas binárias (imagens) — text() corromperia
  const responseBody = await backendResponse.arrayBuffer();
  const responseHeaders: Record<string, string> = {
    "Content-Type": backendResponse.headers.get("content-type") ?? "application/json",
  };
  const cacheControl = backendResponse.headers.get("cache-control");
  if (cacheControl) responseHeaders["Cache-Control"] = cacheControl;
  const etag = backendResponse.headers.get("etag");
  if (etag) responseHeaders["ETag"] = etag;

  const response = new NextResponse(backendResponse.status === 304 ? null : responseBody, {
    status: backendResponse.status,
    headers: responseHeaders,
  });
  if (!isPublic && backendResponse.status === 401) {
    clearSessionCookie(response);
  }
  return response;
}

export const GET = proxy;
export const POST = proxy;
export const PUT = proxy;
export const DELETE = proxy;
