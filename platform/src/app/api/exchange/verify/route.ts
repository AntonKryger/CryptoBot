import { NextRequest, NextResponse } from "next/server";
import { createServerSupabaseClient } from "@/lib/supabase/server";
import { verifyCsrf } from "@/lib/csrf";
import { rateLimit, getRateLimitKey, rateLimitResponse } from "@/lib/rate-limit";
import { EXCHANGE_PROVIDERS, type ExchangeId } from "@/lib/exchanges";

export async function POST(request: NextRequest) {
  if (!verifyCsrf(request)) {
    return NextResponse.json({ error: "Forbidden" }, { status: 403 });
  }
  const rl = rateLimit(getRateLimitKey(request, "exchange-verify"), 10, 60_000);
  if (!rl.allowed) return rateLimitResponse(rl.retryAfterMs);

  try {
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
    const { exchange, environment, credentials } = body as {
      exchange: string;
      environment: string;
      credentials: Record<string, string>;
    };

    // Validate exchange
    const provider = EXCHANGE_PROVIDERS[exchange as ExchangeId];
    if (!provider) {
      return NextResponse.json(
        { error: "Unknown exchange" },
        { status: 400 }
      );
    }

    if (provider.status !== "active") {
      return NextResponse.json(
        { error: `${provider.name} is not yet available. Coming soon!` },
        { status: 400 }
      );
    }

    // Validate environment
    if (provider.hasEnvironments && !["demo", "live"].includes(environment)) {
      return NextResponse.json(
        { error: "Environment must be 'demo' or 'live'" },
        { status: 400 }
      );
    }

    // Validate all required credential fields are present and non-empty
    for (const field of provider.credentialFields) {
      const value = credentials?.[field.key];
      if (!value || value.trim().length === 0) {
        return NextResponse.json(
          { error: `${field.label} cannot be empty` },
          { status: 400 }
        );
      }
    }

    // Exchange-specific verification
    if (exchange === "capital_com") {
      // TODO: Real Capital.com API verification
      // In production, this would make a test session request to:
      //   Demo: https://demo-api-capital.backend-capital.com/api/v1/session
      //   Live: https://api-capital.backend-capital.com/api/v1/session
      // with headers: X-CAP-API-KEY, body: { identifier, password }
      return NextResponse.json({ success: true });
    }

    // Coming-soon exchanges should never reach here (blocked above),
    // but just in case:
    return NextResponse.json(
      { error: `Verification for ${provider.name} is not yet implemented` },
      { status: 400 }
    );
  } catch (error) {
    console.error("Exchange verify error:", error);
    return NextResponse.json(
      { error: "Internal server error" },
      { status: 500 }
    );
  }
}
