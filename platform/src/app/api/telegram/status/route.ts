import { NextResponse } from "next/server";
import { createServerSupabaseClient } from "@/lib/supabase/server";

export async function GET() {
  const supabase = createServerSupabaseClient();

  const {
    data: { user },
    error: authError,
  } = await supabase.auth.getUser();

  if (authError || !user) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  const { data, error } = await supabase
    .from("telegram_connections")
    .select("chat_id, is_verified, code_expires_at")
    .eq("user_id", user.id)
    .single();

  if (error || !data) {
    return NextResponse.json({
      connected: false,
      chatId: null,
      codeExpired: false,
    });
  }

  const codeExpired = data.code_expires_at
    ? new Date(data.code_expires_at) < new Date()
    : false;

  return NextResponse.json({
    connected: data.is_verified && !!data.chat_id,
    chatId: data.chat_id,
    codeExpired,
  });
}
