import { NextResponse, type NextRequest } from "next/server";
import { verifySyncSecret } from "@/lib/sync-auth";
import { createAdminClient } from "@/lib/supabase/admin";
import { rateLimit, getRateLimitKey, rateLimitResponse } from "@/lib/rate-limit";

export async function POST(request: NextRequest) {
  const rl = rateLimit(getRateLimitKey(request, "sync-hb"), 120, 60_000);
  if (!rl.allowed) return rateLimitResponse(rl.retryAfterMs);

  if (!verifySyncSecret(request)) {
    return NextResponse.json({ error: "Forbidden" }, { status: 403 });
  }

  const body = await request.json().catch(() => null);

  if (!body || !body.botInstanceId || !body.timestamp) {
    return NextResponse.json(
      { error: "Missing botInstanceId or timestamp" },
      { status: 400 }
    );
  }

  const supabase = createAdminClient();

  const { error } = await supabase
    .from("bot_instances")
    .update({ last_heartbeat: body.timestamp })
    .eq("id", body.botInstanceId);

  if (error) {
    return NextResponse.json(
      { error: "Failed to update heartbeat" },
      { status: 500 }
    );
  }

  return NextResponse.json({ ok: true });
}
