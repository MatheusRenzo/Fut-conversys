import { NextRequest, NextResponse } from "next/server";
import { BACKEND_API_URL, setSessionCookie } from "@/lib/server-auth";

export async function POST(request: NextRequest) {
  const body = await request.text();
  const backendResponse = await fetch(`${BACKEND_API_URL}/api/auth/register`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body,
  });

  const data = await backendResponse.json();
  if (!backendResponse.ok) {
    return NextResponse.json(data, { status: backendResponse.status });
  }

  const response = NextResponse.json({ user: data.user }, { status: 201 });
  setSessionCookie(response, data.token);
  return response;
}
