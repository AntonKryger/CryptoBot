import { NextRequest, NextResponse } from "next/server";
import { rateLimit, getRateLimitKey, rateLimitResponse } from "@/lib/rate-limit";

// PlatformData service on VPS — dedicated Kraken API, isolated from bots
const PLATFORM_DATA_URL = process.env.PLATFORM_DATA_URL;

// Fallback: Kraken public API (if PlatformData container not available)
const KRAKEN_API = "https://api.kraken.com/0/public";

const SYMBOL_ALIASES: Record<string, string> = { BTC: "XBT" };

const RESOLUTION_TO_MINUTES: Record<string, number> = {
  MINUTE_1: 1, MINUTE_5: 5, MINUTE_15: 15, MINUTE_30: 30,
  HOUR: 60, HOUR_4: 240, DAY: 1440, WEEK: 10080,
};

const ALLOWED_RESOLUTIONS = Object.keys(RESOLUTION_TO_MINUTES);

function validateEpic(epic: string): string | null {
  const normalized = epic.replace("/", "").toUpperCase();
  if (!/^[A-Z0-9]{3,15}$/.test(normalized)) return null;
  return normalized;
}

function epicToKrakenPair(epic: string): string {
  let result = epic;
  for (const [from, to] of Object.entries(SYMBOL_ALIASES)) {
    if (result.startsWith(from)) {
      result = to + result.slice(from.length);
    }
  }
  return result;
}

export async function GET(request: NextRequest) {
  const rl = rateLimit(getRateLimitKey(request, "prices"), 30, 60_000);
  if (!rl.allowed) return rateLimitResponse(rl.retryAfterMs);

  const { searchParams } = new URL(request.url);
  const epicRaw = searchParams.get("epic") || "BTCUSD";
  const resolution = searchParams.get("resolution") || "HOUR";
  const maxRaw = parseInt(searchParams.get("max") || "200", 10);
  const max = Math.min(Number.isNaN(maxRaw) ? 200 : maxRaw, 720);

  const epic = validateEpic(epicRaw);
  if (!epic) {
    return NextResponse.json({ error: "Invalid pair format" }, { status: 400 });
  }
  if (!ALLOWED_RESOLUTIONS.includes(resolution)) {
    return NextResponse.json({ error: "Invalid resolution" }, { status: 400 });
  }

  // --- Route 1: PlatformData container (preferred) ---
  if (PLATFORM_DATA_URL) {
    try {
      const url = new URL(`${PLATFORM_DATA_URL}/api/prices`);
      url.searchParams.set("epic", epic);
      url.searchParams.set("resolution", resolution);
      url.searchParams.set("limit", String(max));

      const resp = await fetch(url.toString(), { cache: "no-store" });
      if (resp.ok) {
        const data = await resp.json();
        return NextResponse.json(data, {
          headers: { "Cache-Control": "public, max-age=10" },
        });
      }
      console.error("[prices] PlatformData responded with", resp.status);
      // Fall through to Kraken direct
    } catch (err) {
      console.error("[prices] PlatformData unreachable, falling back to Kraken:", err);
    }
  }

  // --- Route 2: Kraken public API (fallback) ---
  const pair = epicToKrakenPair(epic);
  const interval = RESOLUTION_TO_MINUTES[resolution];
  const now = Math.floor(Date.now() / 1000);
  const since = now - max * interval * 60;

  try {
    const url = new URL(`${KRAKEN_API}/OHLC`);
    url.searchParams.set("pair", pair);
    url.searchParams.set("interval", String(interval));
    url.searchParams.set("since", String(since));

    const resp = await fetch(url.toString(), { cache: "no-store" });

    if (!resp.ok) {
      return NextResponse.json(
        { error: "Price data temporarily unavailable" },
        { status: 502 }
      );
    }

    const data = await resp.json();

    if (data.error && data.error.length > 0) {
      return NextResponse.json(
        { error: "Unknown or unsupported coin pair" },
        { status: 400 }
      );
    }

    const resultKeys = Object.keys(data.result).filter((k) => k !== "last");
    if (resultKeys.length === 0) {
      return NextResponse.json({ candles: [] });
    }

    const rawCandles = data.result[resultKeys[0]];
    const candles = rawCandles
      .slice(-max)
      .map((c: (string | number)[]) => ({
        time: Number(c[0]),
        open: parseFloat(c[1] as string),
        high: parseFloat(c[2] as string),
        low: parseFloat(c[3] as string),
        close: parseFloat(c[4] as string),
        volume: parseFloat(c[6] as string),
      }));

    return NextResponse.json(
      { candles },
      { headers: { "Cache-Control": "public, max-age=10" } }
    );
  } catch {
    return NextResponse.json(
      { error: "Price data temporarily unavailable" },
      { status: 502 }
    );
  }
}
