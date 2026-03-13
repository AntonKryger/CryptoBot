import { NextRequest, NextResponse } from "next/server";
import { createServerSupabaseClient } from "@/lib/supabase/server";

export async function POST(request: NextRequest) {
  try {
    // Authenticate user
    if (
      process.env.NEXT_PUBLIC_SUPABASE_URL &&
      process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY
    ) {
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
    }

    const body = await request.json();
    const { environment, apiKey, apiPassword, identifier } = body;

    // Validate required fields
    if (!environment || !apiKey || !apiPassword || !identifier) {
      return NextResponse.json(
        { error: "All fields are required: environment, apiKey, apiPassword, identifier" },
        { status: 400 }
      );
    }

    if (!["demo", "live"].includes(environment)) {
      return NextResponse.json(
        { error: "Environment must be 'demo' or 'live'" },
        { status: 400 }
      );
    }

    if (apiKey.trim().length === 0) {
      return NextResponse.json(
        { error: "API Key cannot be empty" },
        { status: 400 }
      );
    }

    if (apiPassword.trim().length === 0) {
      return NextResponse.json(
        { error: "API Password cannot be empty" },
        { status: 400 }
      );
    }

    if (identifier.trim().length === 0) {
      return NextResponse.json(
        { error: "Identifier cannot be empty" },
        { status: 400 }
      );
    }

    // TODO: Real Capital.com API verification
    // For now, validate that fields are non-empty and return success.
    // In production, this would make a test session request to:
    //   Demo: https://demo-api-capital.backend-capital.com/api/v1/session
    //   Live: https://api-capital.backend-capital.com/api/v1/session
    // with headers: X-CAP-API-KEY, body: { identifier, password }

    return NextResponse.json({ success: true });
  } catch (error) {
    console.error("Exchange verify error:", error);
    return NextResponse.json(
      { error: "Internal server error" },
      { status: 500 }
    );
  }
}
