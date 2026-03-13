import { NextResponse, type NextRequest } from "next/server";
import { verifySyncSecret } from "@/lib/sync-auth";
import { createAdminClient } from "@/lib/supabase/admin";

export async function POST(request: NextRequest) {
  if (!verifySyncSecret(request)) {
    return NextResponse.json({ error: "Forbidden" }, { status: 403 });
  }

  const body = await request.json().catch(() => null);

  if (!body || !body.chatId || !body.code) {
    return NextResponse.json(
      { error: "Missing chatId or code" },
      { status: 400 }
    );
  }

  const supabase = createAdminClient();

  // Find matching, non-expired code
  const { data, error } = await supabase
    .from("telegram_connections")
    .select("id, user_id, code_expires_at")
    .eq("verification_code", body.code)
    .eq("is_verified", false)
    .single();

  if (error || !data) {
    return NextResponse.json(
      { error: "Invalid or expired code" },
      { status: 404 }
    );
  }

  // Check expiry
  if (new Date(data.code_expires_at) < new Date()) {
    return NextResponse.json(
      { error: "Code has expired" },
      { status: 410 }
    );
  }

  // Mark as verified
  const { error: updateError } = await supabase
    .from("telegram_connections")
    .update({
      chat_id: String(body.chatId),
      is_verified: true,
      verification_code: null,
      code_expires_at: null,
      updated_at: new Date().toISOString(),
    })
    .eq("id", data.id);

  if (updateError) {
    return NextResponse.json(
      { error: "Failed to verify" },
      { status: 500 }
    );
  }

  return NextResponse.json({ success: true, userId: data.user_id });
}
