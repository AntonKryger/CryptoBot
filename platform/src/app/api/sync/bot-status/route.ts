import { NextResponse, type NextRequest } from "next/server";
import { verifySyncSecret } from "@/lib/sync-auth";
import { createAdminClient } from "@/lib/supabase/admin";
import { rateLimit, getRateLimitKey, rateLimitResponse } from "@/lib/rate-limit";

export async function POST(request: NextRequest) {
  const rl = rateLimit(getRateLimitKey(request, "sync-status"), 60, 60_000);
  if (!rl.allowed) return rateLimitResponse(rl.retryAfterMs);

  if (!verifySyncSecret(request)) {
    return NextResponse.json({ error: "Forbidden" }, { status: 403 });
  }

  const body = await request.json().catch(() => null);

  if (!body || !body.botInstanceId) {
    return NextResponse.json(
      { error: "Missing botInstanceId" },
      { status: 400 }
    );
  }

  const supabase = createAdminClient();

  const updateData: Record<string, unknown> = {};
  if (body.status !== undefined) updateData.status = body.status;
  if (body.uptimePercent !== undefined) updateData.uptime_percent = body.uptimePercent;

  if (Object.keys(updateData).length === 0) {
    return NextResponse.json(
      { error: "No fields to update" },
      { status: 400 }
    );
  }

  const { error } = await supabase
    .from("bot_instances")
    .update(updateData)
    .eq("id", body.botInstanceId);

  if (error) {
    return NextResponse.json(
      { error: "Failed to update bot status" },
      { status: 500 }
    );
  }

  return NextResponse.json({ ok: true });
}
