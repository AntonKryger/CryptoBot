import { NextResponse, type NextRequest } from "next/server";
import { verifySyncSecret } from "@/lib/sync-auth";
import { createAdminClient } from "@/lib/supabase/admin";
import { rateLimit, getRateLimitKey, rateLimitResponse } from "@/lib/rate-limit";

export async function GET(request: NextRequest) {
  const rl = rateLimit(getRateLimitKey(request, "sync-config"), 60, 60_000);
  if (!rl.allowed) return rateLimitResponse(rl.retryAfterMs);

  if (!verifySyncSecret(request)) {
    return NextResponse.json({ error: "Forbidden" }, { status: 403 });
  }

  const botInstanceId = request.nextUrl.searchParams.get("botInstanceId");

  if (!botInstanceId) {
    return NextResponse.json(
      { error: "Missing botInstanceId query parameter" },
      { status: 400 }
    );
  }

  const supabase = createAdminClient();

  const { data, error } = await supabase
    .from("bot_instances")
    .select("is_suspended, suspended_reason, status")
    .eq("id", botInstanceId)
    .single();

  if (error || !data) {
    return NextResponse.json(
      { error: "Bot instance not found" },
      { status: 404 }
    );
  }

  return NextResponse.json({
    is_suspended: data.is_suspended,
    suspended_reason: data.suspended_reason,
    status: data.status,
  });
}
