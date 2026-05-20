import { NextResponse } from "next/server";
import { BACKEND_API_URL, clearSessionCookie, getSessionToken } from "@/lib/server-auth";

export async function GET() {
  const token = await getSessionToken();
  if (!token) {
    return NextResponse.json({ detail: "Sessão expirada" }, { status: 401 });
  }

  const backendResponse = await fetch(`${BACKEND_API_URL}/api/me`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  const data = await backendResponse.json();
  const response = NextResponse.json(data, { status: backendResponse.status });
  if (backendResponse.status === 401) {
    clearSessionCookie(response);
  }
  return response;
}
