import { NextRequest, NextResponse } from "next/server";
import Anthropic from "@anthropic-ai/sdk";
import { rateLimit, getRateLimitKey, rateLimitResponse } from "@/lib/rate-limit";

const ANTHROPIC_API_KEY = process.env.ANTHROPIC_API_KEY;

interface Candle {
  time: number;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

function summarizeCandles(candles: Candle[], coin: string): string {
  if (!candles.length) return "No data available.";

  const last = candles[candles.length - 1];
  const first = candles[0];
  const high = Math.max(...candles.map((c) => c.high));
  const low = Math.min(...candles.map((c) => c.low));
  const totalVolume = candles.reduce((sum, c) => sum + c.volume, 0);
  const changePct = ((last.close - first.open) / first.open) * 100;

  // Recent candles (last 20) for detailed analysis
  const recent = candles.slice(-20);
  const recentData = recent
    .map((c) => {
      const d = new Date(c.time * 1000);
      const dir = c.close >= c.open ? "BULL" : "BEAR";
      const bodyPct = Math.abs(((c.close - c.open) / c.open) * 100).toFixed(3);
      return `${d.toISOString().slice(0, 16)} O:${c.open} H:${c.high} L:${c.low} C:${c.close} V:${c.volume.toFixed(2)} ${dir} body:${bodyPct}%`;
    })
    .join("\n");

  // Key levels
  const closes = candles.map((c) => c.close);
  const highs = candles.map((c) => c.high);
  const lows = candles.map((c) => c.low);

  // Simple swing detection
  const swingHighs: number[] = [];
  const swingLows: number[] = [];
  for (let i = 2; i < candles.length - 2; i++) {
    if (highs[i] > highs[i - 1] && highs[i] > highs[i - 2] && highs[i] > highs[i + 1] && highs[i] > highs[i + 2]) {
      swingHighs.push(highs[i]);
    }
    if (lows[i] < lows[i - 1] && lows[i] < lows[i - 2] && lows[i] < lows[i + 1] && lows[i] < lows[i + 2]) {
      swingLows.push(lows[i]);
    }
  }

  // Fibonacci from range
  const fibHigh = Math.max(...highs.slice(-50));
  const fibLow = Math.min(...lows.slice(-50));
  const fibRange = fibHigh - fibLow;
  const fibs = [0.236, 0.382, 0.5, 0.618, 0.786].map((level) => ({
    level,
    price: fibHigh - fibRange * level,
  }));

  return `
COIN: ${coin}
PERIOD: ${candles.length} candles
CURRENT PRICE: ${last.close}
OPEN (first candle): ${first.open}
CHANGE: ${changePct.toFixed(2)}%
RANGE HIGH: ${high}
RANGE LOW: ${low}
TOTAL VOLUME: ${totalVolume.toFixed(2)}

SWING HIGHS (resistance): ${swingHighs.slice(-5).join(", ") || "none detected"}
SWING LOWS (support): ${swingLows.slice(-5).join(", ") || "none detected"}

FIBONACCI LEVELS (from recent ${Math.min(50, candles.length)} candle range ${fibHigh} to ${fibLow}):
${fibs.map((f) => `  ${f.level}: ${f.price.toFixed(2)}`).join("\n")}

LAST 20 CANDLES (most recent at bottom):
${recentData}
`.trim();
}

const SYSTEM_PROMPT = `Du er en erfaren krypto-analytiker der analyserer live chart-data fra Kraken.

Regler:
- Svar ALTID på dansk
- Vær konkret med priser og niveauer — du har de rigtige data
- Brug teknisk analyse: trend, S/R, Fibonacci, candlestick patterns, volume
- Hold svar korte og actionable (max 150 ord)
- Brug **bold** til key levels og vigtige begreber
- Giv altid en retningsvurdering (bullish/bearish/neutral)
- Nævn specifikke priser fra dataen
- Du er IKKE en bot med faste svar. Du analyserer de faktiske data du modtager.
- Sig aldrig "jeg kan ikke se chartet" — du HAR dataen.`;

export async function POST(request: NextRequest) {
  // Rate limit: 10 requests per minute per user
  const rl = rateLimit(getRateLimitKey(request, "chart-ai"), 10, 60_000);
  if (!rl.allowed) return rateLimitResponse(rl.retryAfterMs);

  if (!ANTHROPIC_API_KEY) {
    return NextResponse.json(
      { error: "AI analysis not configured" },
      { status: 503 }
    );
  }

  try {
    const body = await request.json();
    const { question, coin, candles, timeframe } = body as {
      question: string;
      coin: string;
      candles: Candle[];
      timeframe: string;
    };

    if (!question || !coin) {
      return NextResponse.json({ error: "Missing question or coin" }, { status: 400 });
    }

    // Input validation — prevent cost abuse
    if (typeof question !== "string" || question.length > 500) {
      return NextResponse.json({ error: "Question too long (max 500 chars)" }, { status: 400 });
    }
    if (!/^[A-Z0-9/]{3,15}$/i.test(coin)) {
      return NextResponse.json({ error: "Invalid coin" }, { status: 400 });
    }
    if (Array.isArray(candles) && candles.length > 500) {
      return NextResponse.json({ error: "Too many candles (max 500)" }, { status: 400 });
    }

    const chartContext = candles?.length
      ? summarizeCandles(candles, coin)
      : `COIN: ${coin}\nNo candle data available.`;

    const client = new Anthropic({ apiKey: ANTHROPIC_API_KEY });

    const message = await client.messages.create({
      model: "claude-haiku-4-5-20251001",
      max_tokens: 512,
      system: SYSTEM_PROMPT,
      messages: [
        {
          role: "user",
          content: `Timeframe: ${timeframe || "HOUR"}\n\n${chartContext}\n\nBrugerens spørgsmål: ${question}`,
        },
      ],
    });

    const content = message.content[0];
    const text = content.type === "text" ? content.text : "";

    return NextResponse.json({ response: text });
  } catch (err) {
    console.error("[chart-analysis] Error:", err);
    return NextResponse.json(
      { error: "AI analysis failed" },
      { status: 500 }
    );
  }
}
