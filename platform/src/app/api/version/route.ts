import { NextResponse } from "next/server";

export async function GET() {
  return NextResponse.json({
    commit: process.env.VERCEL_GIT_COMMIT_SHA || "unknown",
    message: process.env.VERCEL_GIT_COMMIT_MESSAGE || "unknown",
    time: new Date().toISOString(),
  });
}
