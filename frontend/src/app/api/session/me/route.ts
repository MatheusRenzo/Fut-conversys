import { NextResponse } from "next/server";
import { BACKEND_API_URL, getSessionToken } from "@/lib/server-auth";

export async function GET() {
  const token = await getSessionToken();
  if (!token) {
    return NextResponse.json({ detail: "Sessão expirada" }, { status: 401 });
  }

  const backendResponse = await fetch(`${BACKEND_API_URL}/api/me`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  const data = await backendResponse.json();
  return NextResponse.json(data, { status: backendResponse.status });
}
