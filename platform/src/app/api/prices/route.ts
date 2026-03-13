import { NextRequest, NextResponse } from "next/server";

const DEMO_URL = "https://demo-api-capital.backend-capital.com";

const ALLOWED_EPICS = ["BTCUSD", "ETHUSD", "SOLUSD", "AVAXUSD", "LINKUSD", "LTCUSD"];
const ALLOWED_RESOLUTIONS = ["MINUTE_15", "HOUR", "HOUR_4", "DAY"];

// Session cache — reuse across requests
let sessionCache: {
  cst: string;
  securityToken: string;
  expiresAt: number;
} | null = null;

async function getSession(): Promise<{ cst: string; securityToken: string }> {
  // Return cached session if still valid (refresh every 8 minutes)
  if (sessionCache && Date.now() < sessionCache.expiresAt) {
    return { cst: sessionCache.cst, securityToken: sessionCache.securityToken };
  }

  const email = process.env.CAPITAL_EMAIL;
  const password = process.env.CAPITAL_PASSWORD;
  const apiKey = process.env.CAPITAL_API_KEY;

  if (!email || !password || !apiKey) {
    throw new Error("Capital.com credentials not configured");
  }

  const resp = await fetch(`${DEMO_URL}/api/v1/session`, {
    method: "POST",
    headers: {
      "X-CAP-API-KEY": apiKey,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      identifier: email,
      password: password,
      encryptedPassword: false,
    }),
  });

  if (!resp.ok) {
    throw new Error(`Capital.com session failed: ${resp.status}`);
  }

  const cst = resp.headers.get("CST") || "";
  const securityToken = resp.headers.get("X-SECURITY-TOKEN") || "";

  sessionCache = {
    cst,
    securityToken,
    expiresAt: Date.now() + 8 * 60 * 1000, // 8 min
  };

  return { cst, securityToken };
}

export async function GET(request: NextRequest) {
  const { searchParams } = new URL(request.url);
  const epic = searchParams.get("epic") || "BTCUSD";
  const resolution = searchParams.get("resolution") || "HOUR";
  const max = Math.min(parseInt(searchParams.get("max") || "200"), 500);

  // Validate inputs
  if (!ALLOWED_EPICS.includes(epic)) {
    return NextResponse.json({ error: `Invalid epic: ${epic}` }, { status: 400 });
  }
  if (!ALLOWED_RESOLUTIONS.includes(resolution)) {
    return NextResponse.json({ error: `Invalid resolution: ${resolution}` }, { status: 400 });
  }

  try {
    const { cst, securityToken } = await getSession();
    const apiKey = process.env.CAPITAL_API_KEY!;

    const priceResp = await fetch(
      `${DEMO_URL}/api/v1/prices/${epic}?resolution=${resolution}&max=${max}`,
      {
        headers: {
          "X-CAP-API-KEY": apiKey,
          CST: cst,
          "X-SECURITY-TOKEN": securityToken,
        },
      }
    );

    if (!priceResp.ok) {
      // Session expired — clear cache and retry once
      if (priceResp.status === 401) {
        sessionCache = null;
        const newSession = await getSession();
        const retryResp = await fetch(
          `${DEMO_URL}/api/v1/prices/${epic}?resolution=${resolution}&max=${max}`,
          {
            headers: {
              "X-CAP-API-KEY": apiKey,
              CST: newSession.cst,
              "X-SECURITY-TOKEN": newSession.securityToken,
            },
          }
        );
        if (!retryResp.ok) {
          return NextResponse.json(
            { error: `Capital.com API error: ${retryResp.status}` },
            { status: 502 }
          );
        }
        const retryData = await retryResp.json();
        return NextResponse.json(transformPrices(retryData), {
          headers: { "Cache-Control": "public, max-age=30" },
        });
      }

      return NextResponse.json(
        { error: `Capital.com API error: ${priceResp.status}` },
        { status: 502 }
      );
    }

    const data = await priceResp.json();
    return NextResponse.json(transformPrices(data), {
      headers: { "Cache-Control": "public, max-age=30" },
    });
  } catch (err) {
    console.error("[prices] Error:", err);
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "Unknown error" },
      { status: 500 }
    );
  }
}

function transformPrices(data: Record<string, unknown>): {
  candles: Array<{
    time: number;
    open: number;
    high: number;
    low: number;
    close: number;
    volume: number;
  }>;
} {
  const prices = (data.prices || []) as Array<Record<string, unknown>>;

  const candles = prices.map((p) => {
    // Capital.com returns snapshotTime as "2026/03/13 14:00:00"
    const timeStr = p.snapshotTime as string;
    const timestamp = Math.floor(new Date(timeStr.replace(/\//g, "-")).getTime() / 1000);

    const openPrice = p.openPrice as Record<string, number>;
    const highPrice = p.highPrice as Record<string, number>;
    const lowPrice = p.lowPrice as Record<string, number>;
    const closePrice = p.closePrice as Record<string, number>;

    return {
      time: timestamp,
      open: openPrice?.mid ?? openPrice?.ask ?? 0,
      high: highPrice?.mid ?? highPrice?.ask ?? 0,
      low: lowPrice?.mid ?? lowPrice?.ask ?? 0,
      close: closePrice?.mid ?? closePrice?.ask ?? 0,
      volume: (p.lastTradedVolume as number) || 0,
    };
  });

  return { candles };
}
