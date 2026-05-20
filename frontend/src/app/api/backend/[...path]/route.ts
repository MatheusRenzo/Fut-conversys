import { NextRequest, NextResponse } from "next/server";
import { BACKEND_API_URL, clearSessionCookie, getSessionToken } from "@/lib/server-auth";

const PUBLIC_BACKEND_PATHS = new Set([
  "api/auth/microsoft/config",
  "api/health",
]);

async function proxy(request: NextRequest, { params }: { params: Promise<{ path: string[] }> }) {
  const { path } = await params;
  const backendPath = path.join("/");
  const isPublic = PUBLIC_BACKEND_PATHS.has(backendPath);
  const token = await getSessionToken();

  if (!isPublic && !token) {
    return NextResponse.json({ detail: "Sessão expirada" }, { status: 401 });
  }

  const target = new URL(`/${backendPath}${request.nextUrl.search}`, BACKEND_API_URL);
  const headers = new Headers();
  const contentType = request.headers.get("content-type");
  if (contentType) headers.set("Content-Type", contentType);
  if (token) headers.set("Authorization", `Bearer ${token}`);

  const backendResponse = await fetch(target, {
    method: request.method,
    headers,
    body: ["GET", "HEAD"].includes(request.method) ? undefined : await request.text(),
  });

  const responseText = await backendResponse.text();
  const response = new NextResponse(responseText, {
    status: backendResponse.status,
    headers: {
      "Content-Type": backendResponse.headers.get("content-type") ?? "application/json",
    },
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
