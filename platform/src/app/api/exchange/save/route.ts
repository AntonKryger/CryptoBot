import { NextRequest, NextResponse } from "next/server";
import { createServerSupabaseClient } from "@/lib/supabase/server";
import { encrypt } from "@/lib/crypto";
import { verifyCsrf } from "@/lib/csrf";
import { rateLimit, getRateLimitKey, rateLimitResponse } from "@/lib/rate-limit";

export async function POST(request: NextRequest) {
  if (!verifyCsrf(request)) {
    return NextResponse.json({ error: "Forbidden" }, { status: 403 });
  }
  const rl = rateLimit(getRateLimitKey(request, "exchange-save"), 10, 60_000);
  if (!rl.allowed) return rateLimitResponse(rl.retryAfterMs);

  try {
    // Authenticate user
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

    // Encrypt credentials
    const apiKeyEncrypted = await encrypt(apiKey);
    const apiPasswordEncrypted = await encrypt(apiPassword);
    const identifierEncrypted = await encrypt(identifier);

    // Check for existing account with same environment
    const { data: existing } = await supabase
      .from("exchange_accounts")
      .select("id")
      .eq("user_id", user.id)
      .eq("environment", environment)
      .single();

    let accountId: string;

    if (existing) {
      // Update existing account
      const { data, error } = await supabase
        .from("exchange_accounts")
        .update({
          api_key_encrypted: apiKeyEncrypted,
          api_password_encrypted: apiPasswordEncrypted,
          identifier_encrypted: identifierEncrypted,
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
      // Insert new account
      const { data, error } = await supabase
        .from("exchange_accounts")
        .insert({
          user_id: user.id,
          exchange: "capital_com",
          environment,
          api_key_encrypted: apiKeyEncrypted,
          api_password_encrypted: apiPasswordEncrypted,
          identifier_encrypted: identifierEncrypted,
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
