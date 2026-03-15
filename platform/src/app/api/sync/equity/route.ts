import { NextResponse, type NextRequest } from "next/server";
import { verifySyncSecret } from "@/lib/sync-auth";
import { createAdminClient } from "@/lib/supabase/admin";
import { rateLimit, getRateLimitKey, rateLimitResponse } from "@/lib/rate-limit";

export async function POST(request: NextRequest) {
  const rl = rateLimit(getRateLimitKey(request, "sync-equity"), 60, 60_000);
  if (!rl.allowed) return rateLimitResponse(rl.retryAfterMs);

  if (!verifySyncSecret(request)) {
    return NextResponse.json({ error: "Forbidden" }, { status: 403 });
  }

  const body = await request.json().catch(() => null);

  if (!body || !body.userId || body.equity == null) {
    return NextResponse.json(
      { error: "Missing required fields (userId, equity)" },
      { status: 400 }
    );
  }

  const supabase = createAdminClient();

  const { error } = await supabase.from("equity_snapshots").insert({
    user_id: body.userId,
    bot_instance_id: body.botInstanceId || null,
    equity: body.equity,
    exchange: body.exchange || "kraken",
    snapshot_at: new Date().toISOString(),
  });

  if (error) {
    console.error("Equity snapshot error:", error);
    return NextResponse.json(
      { error: "Failed to save equity snapshot" },
      { status: 500 }
    );
  }

  return NextResponse.json({ ok: true });
}
