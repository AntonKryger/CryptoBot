import { NextRequest, NextResponse } from "next/server";
import { createServerSupabaseClient } from "@/lib/supabase/server";
import { encrypt } from "@/lib/crypto";
import { verifyCsrf } from "@/lib/csrf";
import { rateLimit, getRateLimitKey, rateLimitResponse } from "@/lib/rate-limit";
import { EXCHANGE_PROVIDERS, type ExchangeId } from "@/lib/exchanges";

export async function POST(request: NextRequest) {
  if (!verifyCsrf(request)) {
    return NextResponse.json({ error: "Forbidden" }, { status: 403 });
  }
  const rl = rateLimit(getRateLimitKey(request, "exchange-save"), 10, 60_000);
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
        { error: `${provider.name} is not yet available` },
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
          { error: `${field.label} is required` },
          { status: 400 }
        );
      }
    }

    // Encrypt each credential value individually
    const credentialsEncrypted: Record<string, string> = {};
    for (const field of provider.credentialFields) {
      credentialsEncrypted[field.key] = await encrypt(credentials[field.key]);
    }

    // Dedup on user_id + exchange + environment
    const env = provider.hasEnvironments ? environment : "live";
    const { data: existing } = await supabase
      .from("exchange_accounts")
      .select("id")
      .eq("user_id", user.id)
      .eq("exchange", exchange)
      .eq("environment", env)
      .single();

    let accountId: string;

    if (existing) {
      const { data, error } = await supabase
        .from("exchange_accounts")
        .update({
          credentials_encrypted: credentialsEncrypted,
          connection_verified: true,
          last_verified_at: new Date().toISOString(),
          is_active: true,
          updated_at: new Date().toISOString(),
        })
        .eq("id", existing.id)
        .select("id")
        .single();

      if (error) {
        console.error("Exchange account update error:", error);
        return NextResponse.json(
          { error: "Failed to update exchange account" },
          { status: 500 }
        );
      }

      accountId = data.id;
    } else {
      const { data, error } = await supabase
        .from("exchange_accounts")
        .insert({
          user_id: user.id,
          exchange,
          environment: env,
          credentials_encrypted: credentialsEncrypted,
          connection_verified: true,
          last_verified_at: new Date().toISOString(),
          is_active: true,
        })
        .select("id")
        .single();

      if (error) {
        console.error("Exchange account insert error:", error);
        return NextResponse.json(
          { error: "Failed to save exchange account" },
          { status: 500 }
        );
      }

      accountId = data.id;
    }

    return NextResponse.json({ id: accountId });
  } catch (error) {
    console.error("Exchange save error:", error);
    return NextResponse.json(
      { error: "Internal server error" },
      { status: 500 }
    );
  }
}
