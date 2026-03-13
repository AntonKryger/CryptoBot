import { NextResponse, type NextRequest } from "next/server";
import { createMiddlewareSupabaseClient } from "@/lib/supabase/middleware";

// Routes accessible without authentication
const PUBLIC_ROUTES = [
  "/",
  "/login",
  "/signup",
  "/callback",
  "/pricing",
  "/verify-2fa",
  "/setup-2fa",
  "/forgot-password",
  "/reset-password",
];

// Routes only accessible when NOT authenticated
const AUTH_ONLY_ROUTES = ["/login", "/signup", "/forgot-password", "/reset-password"];

// Admin-only routes
const ADMIN_ROUTES = ["/admin"];

// Routes that should be skipped entirely
const SKIP_PREFIXES = ["/_next", "/api", "/favicon.ico"];

function shouldSkip(pathname: string): boolean {
  return SKIP_PREFIXES.some((prefix) => pathname.startsWith(prefix));
}

function isPublicRoute(pathname: string): boolean {
  return PUBLIC_ROUTES.includes(pathname);
}

function isAuthOnlyRoute(pathname: string): boolean {
  return AUTH_ONLY_ROUTES.includes(pathname);
}

function isAdminRoute(pathname: string): boolean {
  return ADMIN_ROUTES.some(
    (route) => pathname === route || pathname.startsWith(route + "/")
  );
}

export async function middleware(request: NextRequest) {
  const { pathname } = request.nextUrl;

  if (shouldSkip(pathname)) {
    return NextResponse.next();
  }

  const response = NextResponse.next({ request });

  // Dev mode: no Supabase configured → allow everything
  if (
    !process.env.NEXT_PUBLIC_SUPABASE_URL ||
    !process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY
  ) {
    return response;
  }

  const supabase = createMiddlewareSupabaseClient(request, response);

  // Helper: create redirect that preserves Supabase auth cookies
  function redirectTo(url: string): NextResponse {
    const redirectResponse = NextResponse.redirect(new URL(url, request.url));
    response.cookies.getAll().forEach((cookie) => {
      redirectResponse.cookies.set(cookie);
    });
    return redirectResponse;
  }

  const {
    data: { user },
  } = await supabase.auth.getUser();

  // ─── UNAUTHENTICATED ───
  if (!user) {
    if (isPublicRoute(pathname)) {
      return response;
    }
    return redirectTo(`/login?redirect=${encodeURIComponent(pathname)}`);
  }

  // ─── AUTHENTICATED on auth-only routes → redirect away ───
  if (isAuthOnlyRoute(pathname)) {
    // Owner → admin, others → pricing
    const appRole = (user.app_metadata as Record<string, unknown>)?.role;
    return redirectTo(appRole === "owner" ? "/admin" : "/pricing");
  }

  // ─── AUTHENTICATED on public routes → always allow ───
  if (isPublicRoute(pathname)) {
    return response;
  }

  // ─── OWNER CHECK: use JWT app_metadata (no DB query, no RLS issues) ───
  const appRole = (user.app_metadata as Record<string, unknown>)?.role;
  if (appRole === "owner") {
    // Owner bypasses ALL gates — admin, dashboard, everything
    return response;
  }

  // ─── Non-owner on admin routes ───
  if (isAdminRoute(pathname)) {
    return redirectTo("/pricing");
  }

  // ─── SUBSCRIBER GATES (need profile from DB) ───
  // Always allow checkout and onboarding
  if (pathname === "/checkout" || pathname === "/onboarding") {
    return response;
  }

  // Query profile for subscriber gate checks
  // Use service role if available, fall back to anon (may fail with RLS)
  const serviceRoleKey = process.env.SUPABASE_SERVICE_ROLE_KEY;
  let profileClient;
  if (serviceRoleKey) {
    const { createClient } = await import("@supabase/supabase-js");
    profileClient = createClient(process.env.NEXT_PUBLIC_SUPABASE_URL!, serviceRoleKey);
  } else {
    profileClient = supabase;
  }

  const { data: profile } = await profileClient
    .from("profiles")
    .select("tier, onboarding_completed, subscription_status")
    .eq("id", user.id)
    .single();

  if (!profile) {
    return redirectTo("/pricing");
  }

  // No tier → must pick a plan
  if (!profile.tier) {
    return redirectTo("/pricing");
  }

  // No active subscription → must pay
  if (
    profile.subscription_status === "none" ||
    profile.subscription_status === "canceled"
  ) {
    return redirectTo("/pricing");
  }

  // Active but onboarding not done
  if (
    profile.subscription_status === "active" &&
    !profile.onboarding_completed
  ) {
    return redirectTo("/onboarding");
  }

  return response;
}

export const config = {
  matcher: [
    "/((?!_next/static|_next/image|favicon\\.ico|.*\\.(?:svg|png|jpg|jpeg|gif|webp)$).*)",
  ],
};
