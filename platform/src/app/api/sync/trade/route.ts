import { NextResponse, type NextRequest } from "next/server";
import { verifySyncSecret } from "@/lib/sync-auth";
import { createAdminClient } from "@/lib/supabase/admin";

export async function POST(request: NextRequest) {
  if (!verifySyncSecret(request)) {
    return NextResponse.json({ error: "Forbidden" }, { status: 403 });
  }

  const body = await request.json().catch(() => null);

  if (!body || !body.userId || !body.botInstanceId || !body.epic) {
    return NextResponse.json(
      { error: "Missing required fields (userId, botInstanceId, epic)" },
      { status: 400 }
    );
  }

  const supabase = createAdminClient();

  const { data, error } = await supabase
    .from("trades")
    .insert({
      user_id: body.userId,
      bot_instance_id: body.botInstanceId,
      deal_id: body.dealId || null,
      deal_reference: body.dealReference || null,
      epic: body.epic,
      direction: body.direction,
      size: body.size,
      entry_price: body.entryPrice,
      stop_loss: body.stopLoss || null,
      take_profit: body.takeProfit || null,
      signal_mode: body.signalMode || null,
      signal_data: body.signalData || null,
      status: "open",
      opened_at: new Date().toISOString(),
    })
    .select("id")
    .single();

  if (error) {
    return NextResponse.json(
      { error: "Failed to insert trade" },
      { status: 500 }
    );
  }

  return NextResponse.json({ id: data.id });
}
