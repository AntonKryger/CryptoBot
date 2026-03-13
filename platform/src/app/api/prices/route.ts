import { NextRequest, NextResponse } from "next/server";

// Price data is proxied through the VPS dashboard (port 5000)
// because Capital.com rejects auth from Vercel's serverless IPs.
const VPS_DASHBOARD_URL = process.env.VPS_DASHBOARD_URL || "http://91.98.26.70:5000";

const ALLOWED_EPICS = ["BTCUSD", "ETHUSD", "SOLUSD", "AVAXUSD", "LINKUSD", "LTCUSD"];
const ALLOWED_RESOLUTIONS = ["MINUTE_15", "HOUR", "HOUR_4", "DAY"];

export async function GET(request: NextRequest) {
  const { searchParams } = new URL(request.url);
  const epic = searchParams.get("epic") || "BTCUSD";
  const resolution = searchParams.get("resolution") || "HOUR";
  const max = Math.min(parseInt(searchParams.get("max") || "200"), 500);

  if (!ALLOWED_EPICS.includes(epic)) {
    return NextResponse.json({ error: `Invalid epic: ${epic}` }, { status: 400 });
  }
  if (!ALLOWED_RESOLUTIONS.includes(resolution)) {
    return NextResponse.json({ error: `Invalid resolution: ${resolution}` }, { status: 400 });
  }

  try {
    const resp = await fetch(
      `${VPS_DASHBOARD_URL}/api/prices?epic=${epic}&resolution=${resolution}&max=${max}`,
      { next: { revalidate: 30 } }
    );

    if (!resp.ok) {
      const errorText = await resp.text();
      return NextResponse.json(
        { error: `VPS proxy error: ${resp.status} ${errorText}` },
        { status: 502 }
      );
    }

    const data = await resp.json();
    return NextResponse.json(data, {
      headers: { "Cache-Control": "public, max-age=30" },
    });
  } catch (err) {
    console.error("[prices] VPS proxy error:", err);
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "VPS unreachable" },
      { status: 502 }
    );
  }
}
