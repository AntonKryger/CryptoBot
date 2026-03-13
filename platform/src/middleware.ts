import { NextResponse, type NextRequest } from "next/server";
import { createMiddlewareSupabaseClient } from "@/lib/supabase/middleware";
import type { Profile } from "@/lib/supabase/types";

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

  const {
    data: { user },
  } = await supabase.auth.getUser();

  // ─── UNAUTHENTICATED ───
  if (!user) {
    if (isPublicRoute(pathname)) {
      return response;
    }
    const loginUrl = new URL("/login", request.url);
    loginUrl.searchParams.set("redirect", pathname);
    return NextResponse.redirect(loginUrl);
  }

  // ─── AUTHENTICATED on auth-only routes (login/signup/forgot) → redirect away ───
  if (isAuthOnlyRoute(pathname)) {
    return NextResponse.redirect(new URL("/pricing", request.url));
  }

  // ─── AUTHENTICATED on public routes → always allow ───
  if (isPublicRoute(pathname)) {
    return response;
  }

  // ─── From here: authenticated + protected route → need profile ───
  const { data: profile } = await supabase
    .from("profiles")
    .select("role, has_2fa, tier, onboarding_completed, subscription_status")
    .eq("id", user.id)
    .single<Pick<Profile, "role" | "has_2fa" | "tier" | "onboarding_completed" | "subscription_status">>();

  // No profile → safe fallback to pricing
  if (!profile) {
    if (pathname === "/callback") return response;
    return NextResponse.redirect(new URL("/pricing", request.url));
  }

  // ─── OWNER → bypass all gates ───
  if (profile.role === "owner") {
    if (isAdminRoute(pathname) && !profile.has_2fa) {
      return NextResponse.redirect(new URL("/setup-2fa", request.url));
    }
    return response;
  }

  // ─── Non-owner on admin routes ───
  if (isAdminRoute(pathname)) {
    return NextResponse.redirect(new URL("/pricing", request.url));
  }

  // ─── SUBSCRIBER GATES ───
  // Always allow checkout (that's where they pick/pay for a tier)
  if (pathname === "/checkout") {
    return response;
  }

  // Always allow onboarding
  if (pathname === "/onboarding") {
    return response;
  }

  // No tier → must pick a plan
  if (!profile.tier) {
    return NextResponse.redirect(new URL("/pricing", request.url));
  }

  // Has tier but no active subscription → must pay
  if (
    profile.subscription_status === "none" ||
    profile.subscription_status === "canceled"
  ) {
    return NextResponse.redirect(new URL("/pricing", request.url));
  }

  // Active subscription but onboarding not done → must complete
  if (
    profile.subscription_status === "active" &&
    !profile.onboarding_completed
  ) {
    return NextResponse.redirect(new URL("/onboarding", request.url));
  }

  // All gates passed → allow
  return response;
}

export const config = {
  matcher: [
    "/((?!_next/static|_next/image|favicon\\.ico|.*\\.(?:svg|png|jpg|jpeg|gif|webp)$).*)",
  ],
};
