import { NextRequest, NextResponse } from "next/server";
import { createServerSupabaseClient } from "@/lib/supabase/server";
import { rateLimit, getRateLimitKey, rateLimitResponse } from "@/lib/rate-limit";

const VPS_DASHBOARD_URL = process.env.VPS_DASHBOARD_URL;

export async function GET(request: NextRequest) {
  const rl = rateLimit(getRateLimitKey(request, "leaderboard"), 20, 60_000);
  if (!rl.allowed) return rateLimitResponse(rl.retryAfterMs);

  // Auth check
  const supabase = createServerSupabaseClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();

  if (!user) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  if (!VPS_DASHBOARD_URL) {
    return NextResponse.json(
      { error: "Leaderboard proxy not configured" },
      { status: 503 }
    );
  }

  try {
    const base = VPS_DASHBOARD_URL.replace(/\/+$/, "");
    const resp = await fetch(`${base}/api/leaderboard`, {
      next: { revalidate: 60 },
    });

    if (!resp.ok) {
      console.error("[leaderboard] VPS responded with", resp.status);
      return NextResponse.json(
        { error: "Leaderboard data temporarily unavailable" },
        { status: 502 }
      );
    }

    const data = await resp.json();

    if (!Array.isArray(data)) {
      console.error("[leaderboard] VPS returned non-array data");
      return NextResponse.json(
        { error: "Invalid leaderboard data" },
        { status: 502 }
      );
    }

    return NextResponse.json(data, {
      headers: { "Cache-Control": "public, max-age=60" },
    });
  } catch (err) {
    console.error("[leaderboard] VPS proxy error:", err);
    return NextResponse.json(
      { error: "Leaderboard data temporarily unavailable" },
      { status: 502 }
    );
  }
}
