import { NextResponse, type NextRequest } from "next/server";
import { verifySyncSecret } from "@/lib/sync-auth";
import { createAdminClient } from "@/lib/supabase/admin";
import { rateLimit, getRateLimitKey, rateLimitResponse } from "@/lib/rate-limit";

export async function POST(request: NextRequest) {
  const rl = rateLimit(getRateLimitKey(request, "sync-register"), 10, 60_000);
  if (!rl.allowed) return rateLimitResponse(rl.retryAfterMs);

  if (!verifySyncSecret(request)) {
    return NextResponse.json({ error: "Forbidden" }, { status: 403 });
  }

  const body = await request.json().catch(() => null);

  if (!body || !body.botId || !body.userId) {
    return NextResponse.json(
      { error: "Missing required fields (botId, userId)" },
      { status: 400 }
    );
  }

  const supabase = createAdminClient();

  // Check if bot with same botId + userId already exists (match on name)
  const { data: existing } = await supabase
    .from("bot_instances")
    .select("id")
    .eq("user_id", body.userId)
    .eq("name", body.botId)
    .single();

  if (existing) {
    return NextResponse.json({
      botInstanceId: existing.id,
      alreadyExists: true,
    });
  }

  // Resolve exchange_account_id: use provided, find existing, or auto-create
  let exchangeAccountId = body.exchangeAccountId;

  if (!exchangeAccountId) {
    const exchange = body.exchange || "kraken";

    // Look for existing exchange account for this user + exchange
    const { data: existingAccount } = await supabase
      .from("exchange_accounts")
      .select("id")
      .eq("user_id", body.userId)
      .eq("exchange", exchange)
      .limit(1)
      .single();

    if (existingAccount) {
      exchangeAccountId = existingAccount.id;
    } else {
      // Auto-create a placeholder exchange account (bot-registered, no credentials)
      const { data: newAccount, error: accountError } = await supabase
        .from("exchange_accounts")
        .insert({
          user_id: body.userId,
          exchange,
          environment: "live",
          credentials_encrypted: {},
          connection_verified: false,
          is_active: true,
        })
        .select("id")
        .single();

      if (accountError) {
        console.error("Exchange account auto-create error:", accountError);
        return NextResponse.json(
          { error: "Failed to create exchange account" },
          { status: 500 }
        );
      }

      exchangeAccountId = newAccount.id;
    }
  }

  // Insert new bot instance
  const { data, error } = await supabase
    .from("bot_instances")
    .insert({
      user_id: body.userId,
      exchange_account_id: exchangeAccountId,
      name: body.botId,
      status: "running",
      coins: body.coins || [],
      risk_percent: 1.0,
      max_positions: body.coins?.length || 2,
      adx_minimum: 20.0,
      rr_minimum: 2.0,
    })
    .select("id")
    .single();

  if (error) {
    console.error("Bot register error:", error);
    return NextResponse.json(
      { error: "Failed to register bot" },
      { status: 500 }
    );
  }

  return NextResponse.json({
    botInstanceId: data.id,
    alreadyExists: false,
  });
}
