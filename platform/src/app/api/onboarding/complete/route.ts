import { NextRequest, NextResponse } from "next/server";
import { createServerSupabaseClient } from "@/lib/supabase/server";
import { ALLOWED_COINS } from "@/lib/constants";
import { verifyCsrf } from "@/lib/csrf";

export async function POST(request: NextRequest) {
  if (!verifyCsrf(request)) {
    return NextResponse.json({ error: "Forbidden" }, { status: 403 });
  }

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
    const { botName, coins, riskPercent, maxPositions, exchangeAccountId } =
      body;

    // Validate required fields
    if (!botName || !coins || !riskPercent || !maxPositions || !exchangeAccountId) {
      return NextResponse.json(
        { error: "All fields are required" },
        { status: 400 }
      );
    }

    // Validate bot name
    if (typeof botName !== "string" || botName.trim().length === 0) {
      return NextResponse.json(
        { error: "Bot name cannot be empty" },
        { status: 400 }
      );
    }

    // Validate coins
    if (!Array.isArray(coins) || coins.length === 0) {
      return NextResponse.json(
        { error: "At least one coin must be selected" },
        { status: 400 }
      );
    }

    const allowedSet = new Set(ALLOWED_COINS as readonly string[]);
    for (const coin of coins) {
      if (!allowedSet.has(coin)) {
        return NextResponse.json(
          { error: `Invalid coin: ${coin}` },
          { status: 400 }
        );
      }
    }

    // Validate risk percent
    const risk = Number(riskPercent);
    if (isNaN(risk) || risk < 0.5 || risk > 2.0) {
      return NextResponse.json(
        { error: "Risk percent must be between 0.5 and 2.0" },
        { status: 400 }
      );
    }

    // Validate max positions
    const maxPos = Number(maxPositions);
    if (isNaN(maxPos) || maxPos < 1 || maxPos > 5 || !Number.isInteger(maxPos)) {
      return NextResponse.json(
        { error: "Max positions must be an integer between 1 and 5" },
        { status: 400 }
      );
    }

    // Verify exchange account belongs to this user
    const { data: exchangeAccount, error: exchangeError } = await supabase
      .from("exchange_accounts")
      .select("id")
      .eq("id", exchangeAccountId)
      .eq("user_id", user.id)
      .single();

    if (exchangeError || !exchangeAccount) {
      return NextResponse.json(
        { error: "Exchange account not found" },
        { status: 404 }
      );
    }

    // Create bot instance
    const { error: botError } = await supabase
      .from("bot_instances")
      .insert({
        user_id: user.id,
        exchange_account_id: exchangeAccountId,
        name: botName.trim(),
        status: "stopped",
        coins,
        risk_percent: Math.round(risk * 10) / 10,
        max_positions: maxPos,
        adx_minimum: 20,
        rr_minimum: 2.0,
      });

    if (botError) {
      console.error("Bot instance creation error:", botError);
      return NextResponse.json(
        { error: "Failed to create bot instance" },
        { status: 500 }
      );
    }

    // Mark onboarding as completed
    const { error: profileError } = await supabase
      .from("profiles")
      .update({
        onboarding_completed: true,
        updated_at: new Date().toISOString(),
      })
      .eq("id", user.id);

    if (profileError) {
      console.error("Profile update error:", profileError);
      return NextResponse.json(
        { error: "Failed to update profile" },
        { status: 500 }
      );
    }

    return NextResponse.json({ success: true });
  } catch (error) {
    console.error("Onboarding complete error:", error);
    return NextResponse.json(
      { error: "Internal server error" },
      { status: 500 }
    );
  }
}
