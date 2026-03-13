import { NextRequest, NextResponse } from "next/server";
import { createServerSupabaseClient } from "@/lib/supabase/server";
import { verifyCsrf } from "@/lib/csrf";
import { rateLimit, getRateLimitKey, rateLimitResponse } from "@/lib/rate-limit";

export async function POST(request: NextRequest) {
  if (!verifyCsrf(request)) {
    return NextResponse.json({ error: "Forbidden" }, { status: 403 });
  }
  const rl = rateLimit(getRateLimitKey(request, "exchange-verify"), 10, 60_000);
  if (!rl.allowed) return rateLimitResponse(rl.retryAfterMs);

  try {
    // Authenticate user — always required
    const supabase = createServerSupabaseClient();
    const {
      data: { user },
    } = await supabase.auth.getUser();

    if (!user) {
      return NextResponse.json(
        { error: "Unauthorized" },
        { status: 401 }
      );
    }

    const body = await request.json();
    const { environment, apiKey, apiPassword, identifier } = body;

    // Validate required fields
    if (!environment || !apiKey || !apiPassword || !identifier) {
      return NextResponse.json(
        { error: "All fields are required: environment, apiKey, apiPassword, identifier" },
        { status: 400 }
      );
    }

    if (!["demo", "live"].includes(environment)) {
      return NextResponse.json(
        { error: "Environment must be 'demo' or 'live'" },
        { status: 400 }
      );
    }

    if (apiKey.trim().length === 0) {
      return NextResponse.json(
        { error: "API Key cannot be empty" },
        { status: 400 }
      );
    }

    if (apiPassword.trim().length === 0) {
      return NextResponse.json(
        { error: "API Password cannot be empty" },
        { status: 400 }
      );
    }

    if (identifier.trim().length === 0) {
      return NextResponse.json(
        { error: "Identifier cannot be empty" },
        { status: 400 }
      );
    }

    // TODO: Real Capital.com API verification
    // For now, validate that fields are non-empty and return success.
    // In production, this would make a test session request to:
    //   Demo: https://demo-api-capital.backend-capital.com/api/v1/session
    //   Live: https://api-capital.backend-capital.com/api/v1/session
    // with headers: X-CAP-API-KEY, body: { identifier, password }

    return NextResponse.json({ success: true });
  } catch (error) {
    console.error("Exchange verify error:", error);
    return NextResponse.json(
      { error: "Internal server error" },
      { status: 500 }
    );
  }
}
