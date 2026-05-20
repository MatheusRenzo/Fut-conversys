import { NextRequest, NextResponse } from "next/server";

const protectedRoutes = ["/dashboard", "/events", "/profile", "/me"];

export function middleware(request: NextRequest) {
  const hasSession = Boolean(request.cookies.get("conversys_session")?.value);
  const pathname = request.nextUrl.pathname;
  const isProtected = protectedRoutes.some((route) => pathname === route || pathname.startsWith(`${route}/`));

  if (isProtected && !hasSession) {
    return NextResponse.redirect(new URL("/", request.url));
  }

  if (pathname === "/" && hasSession) {
    return NextResponse.redirect(new URL("/dashboard", request.url));
  }

  return NextResponse.next();
}

export const config = {
  matcher: ["/", "/dashboard/:path*", "/events/:path*", "/profile/:path*", "/me/:path*"],
};
