import { NextResponse, type NextRequest } from "next/server";
import { verifySyncSecret } from "@/lib/sync-auth";
import { createAdminClient } from "@/lib/supabase/admin";

export async function POST(request: NextRequest) {
  if (!verifySyncSecret(request)) {
    return NextResponse.json({ error: "Forbidden" }, { status: 403 });
  }

  const body = await request.json().catch(() => null);

  if (!body || !body.dealId) {
    return NextResponse.json(
      { error: "Missing dealId" },
      { status: 400 }
    );
  }

  const supabase = createAdminClient();

  const { error } = await supabase
    .from("trades")
    .update({
      exit_price: body.exitPrice ?? null,
      profit_loss: body.profitLoss ?? null,
      profit_loss_percent: body.profitLossPercent ?? null,
      status: "closed",
      closed_at: body.closedAt || new Date().toISOString(),
    })
    .eq("deal_id", body.dealId);

  if (error) {
    return NextResponse.json(
      { error: "Failed to close trade" },
      { status: 500 }
    );
  }

  return NextResponse.json({ ok: true });
}
