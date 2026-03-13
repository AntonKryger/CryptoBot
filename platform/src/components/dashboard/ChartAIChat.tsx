"use client";

import { useState, useRef, useEffect } from "react";
import { Send, Bot, User, Loader2 } from "lucide-react";
import { cn } from "@/lib/utils";

interface Message {
  id: string;
  role: "user" | "assistant";
  content: string;
  timestamp: Date;
}

interface ChartAIChatProps {
  selectedCoin: string;
  className?: string;
}

// Mock AI responses based on coin context
function getMockResponse(question: string, coin: string): string {
  const q = question.toLowerCase();
  const coinName = coin.replace("USD", "");

  if (q.includes("trend") || q.includes("retning")) {
    return `**${coinName} Markedsstruktur:**\n\nBaseret på 4H chart ser jeg en serie af Higher Highs og Higher Lows — det er en bullish impulse-struktur.\n\n**Key levels:**\n- Support: Fibonacci 0.618 retracement\n- Resistance: Seneste swing high\n\n**Anbefaling:** Kig efter BUY-entries ved pullbacks til 0.618 Fib-niveau. Undgå at shorte mod strukturen medmindre du ser et klart breakdown.`;
  }

  if (q.includes("support") || q.includes("resistance") || q.includes("s/r")) {
    return `**${coinName} Support/Resistance Niveauer:**\n\n**Resistance zoner:**\n- R1: Seneste swing high (stærkest)\n- R2: Psykologisk rundt tal\n\n**Support zoner:**\n- S1: 0.618 Fibonacci retracement\n- S2: Seneste swing low\n\nDe stærkeste zoner er dem med confluence — hvor Fibonacci, swing points og runde tal mødes.`;
  }

  if (q.includes("elliott") || q.includes("wave") || q.includes("bølge")) {
    return `**${coinName} Elliott Wave Analyse:**\n\nJeg ser en mulig 5-bølge impulsiv struktur:\n- Bølge 1: Første impuls op\n- Bølge 2: Korrektion til 0.618 Fib (typisk)\n- Bølge 3: Stærkeste bevægelse (vi er muligvis her)\n- Bølge 4: Shallow pullback (0.382 Fib)\n- Bølge 5: Final push til target\n\n**Husk:** Bølge 2 retracer typisk 0.618-0.786, og bølge 4 er shallow (0.236-0.382). Hvis pris bryder under bølge 1's top, er tællingen ugyldig.`;
  }

  if (q.includes("fib") || q.includes("fibonacci")) {
    return `**${coinName} Fibonacci Niveauer:**\n\nFra seneste swing low til swing high:\n- 0.236: Svag pullback (trend er stærk)\n- 0.382: Normal retracement\n- 0.500: Midtpunkt\n- **0.618: Golden ratio** — stærkeste support/resistance\n- 0.786: Dyb retracement (sidste chance før reversal)\n\n**Trading strategi:**\nI en uptrend: Sæt buy-orders ved 0.618 med SL under 0.786. TP ved seneste high eller 1.618 extension.`;
  }

  if (q.includes("short") || q.includes("sell")) {
    return `**${coinName} Short Setup Analyse:**\n\nFor at shorte sikkert skal du se:\n1. **Bearish markedsstruktur** (Lower Highs + Lower Lows)\n2. **RSI divergens** ved modstand\n3. **Pris ved key resistance** (Fib 0.618 retrace i downtrend)\n4. **Volume bekræftelse** på rejection\n\n⚠️ **Advarsel:** Short ALDRIG i en bullish impulse medmindre du er ved en MAJOR resistance med stærke reversal-signaler. Strukturen vinder altid.`;
  }

  if (q.includes("buy") || q.includes("køb") || q.includes("long")) {
    return `**${coinName} Long Setup Analyse:**\n\nIdeel BUY-entry kræver:\n1. **Bullish markedsstruktur** (Higher Highs + Higher Lows)\n2. **Pullback til Fibonacci** 0.618 eller S/R zone\n3. **Bullish candle-mønster** ved support (hammer, engulfing)\n4. **MACD/RSI** vender op fra support\n\n**Risk management:** SL under swing low, TP ved næste resistance. Minimum R:R 2:1.`;
  }

  return `**${coinName} Analyse:**\n\nJeg kan hjælpe med:\n- **Trend analyse** — er vi i en impulse eller korrektion?\n- **Support/Resistance** — where are the key levels?\n- **Elliott Wave** — which wave are we in?\n- **Fibonacci** — retracement and extension levels\n- **Entry/Exit** — where to buy/sell?\n\nPrøv at spørge: "Hvad er trenden?" eller "Vis Fibonacci niveauer" eller "Skal jeg shorte her?"`;
}

export function ChartAIChat({ selectedCoin, className }: ChartAIChatProps) {
  const [messages, setMessages] = useState<Message[]>([
    {
      id: "welcome",
      role: "assistant",
      content: `Hej! Jeg er din AI trading-analytiker. Spørg mig om **${selectedCoin.replace("USD", "")}** — trend, support/resistance, Elliott Waves, Fibonacci, eller entry/exit setups.`,
      timestamp: new Date(),
    },
  ]);
  const [input, setInput] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  // Update welcome message when coin changes
  useEffect(() => {
    setMessages([
      {
        id: "welcome",
        role: "assistant",
        content: `Hej! Jeg er din AI trading-analytiker. Spørg mig om **${selectedCoin.replace("USD", "")}** — trend, support/resistance, Elliott Waves, Fibonacci, eller entry/exit setups.`,
        timestamp: new Date(),
      },
    ]);
  }, [selectedCoin]);

  // Auto-scroll to bottom
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const handleSend = async () => {
    const text = input.trim();
    if (!text || isLoading) return;

    const userMsg: Message = {
      id: `user-${Date.now()}`,
      role: "user",
      content: text,
      timestamp: new Date(),
    };

    setMessages((prev) => [...prev, userMsg]);
    setInput("");
    setIsLoading(true);

    // Simulate AI thinking delay
    await new Promise((resolve) => setTimeout(resolve, 800 + Math.random() * 1200));

    const response = getMockResponse(text, selectedCoin);
    const aiMsg: Message = {
      id: `ai-${Date.now()}`,
      role: "assistant",
      content: response,
      timestamp: new Date(),
    };

    setMessages((prev) => [...prev, aiMsg]);
    setIsLoading(false);
    inputRef.current?.focus();
  };

  return (
    <div
      className={cn(
        "rounded-xl border border-border bg-bg-card backdrop-blur-sm shadow-sm flex flex-col",
        className
      )}
    >
      {/* Header */}
      <div className="flex items-center gap-2 px-4 py-3 border-b border-border">
        <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-accent-muted">
          <Bot className="h-4 w-4 text-accent" />
        </div>
        <div>
          <h3 className="text-sm font-semibold text-text-primary">AI Chart Analyst</h3>
          <p className="text-xs text-text-muted">
            Analyserer {selectedCoin.replace("USD", "/USD")}
          </p>
        </div>
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto px-4 py-3 space-y-3 min-h-[300px] max-h-[500px]">
        {messages.map((msg) => (
          <div
            key={msg.id}
            className={cn("flex gap-2", msg.role === "user" ? "justify-end" : "justify-start")}
          >
            {msg.role === "assistant" && (
              <div className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-accent-muted mt-0.5">
                <Bot className="h-3.5 w-3.5 text-accent" />
              </div>
            )}
            <div
              className={cn(
                "max-w-[85%] rounded-lg px-3 py-2 text-sm",
                msg.role === "user"
                  ? "bg-accent text-white"
                  : "bg-bg-card-hover text-text-primary"
              )}
            >
              {msg.content.split("\n").map((line, i) => (
                <p key={i} className={cn(i > 0 && "mt-1")}>
                  {line.split("**").map((part, j) =>
                    j % 2 === 1 ? (
                      <strong key={j} className="font-semibold">
                        {part}
                      </strong>
                    ) : (
                      part
                    )
                  )}
                </p>
              ))}
            </div>
            {msg.role === "user" && (
              <div className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-text-muted/20 mt-0.5">
                <User className="h-3.5 w-3.5 text-text-secondary" />
              </div>
            )}
          </div>
        ))}

        {isLoading && (
          <div className="flex gap-2">
            <div className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-accent-muted mt-0.5">
              <Bot className="h-3.5 w-3.5 text-accent" />
            </div>
            <div className="bg-bg-card-hover rounded-lg px-3 py-2">
              <Loader2 className="h-4 w-4 text-accent animate-spin" />
            </div>
          </div>
        )}

        <div ref={messagesEndRef} />
      </div>

      {/* Input */}
      <div className="border-t border-border px-4 py-3">
        <form
          onSubmit={(e) => {
            e.preventDefault();
            handleSend();
          }}
          className="flex gap-2"
        >
          <input
            ref={inputRef}
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Spørg om trend, S/R, Fibonacci, waves..."
            className={cn(
              "flex-1 rounded-lg border border-border bg-bg-primary px-3 py-2 text-sm",
              "text-text-primary placeholder:text-text-muted",
              "focus:outline-none focus:ring-2 focus:ring-accent/50 focus:border-accent"
            )}
            disabled={isLoading}
          />
          <button
            type="submit"
            disabled={!input.trim() || isLoading}
            className={cn(
              "flex h-9 w-9 shrink-0 items-center justify-center rounded-lg transition-colors",
              input.trim() && !isLoading
                ? "bg-accent text-white hover:bg-accent/90"
                : "bg-bg-card-hover text-text-muted cursor-not-allowed"
            )}
          >
            <Send className="h-4 w-4" />
          </button>
        </form>
      </div>
    </div>
  );
}
