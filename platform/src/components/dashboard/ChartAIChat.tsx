"use client";

import { useState, useRef, useEffect, useCallback } from "react";
import { Send, Bot, User, Loader2 } from "lucide-react";
import { cn } from "@/lib/utils";

interface Message {
  id: string;
  role: "user" | "assistant";
  content: string;
  timestamp: Date;
}

interface ApiCandle {
  time: number;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

interface ChartAIChatProps {
  selectedCoin: string;
  className?: string;
}

export function ChartAIChat({ selectedCoin, className }: ChartAIChatProps) {
  const coinName = selectedCoin.replace("USD", "");

  const [messages, setMessages] = useState<Message[]>([
    {
      id: "welcome",
      role: "assistant",
      content: `Hej! Jeg analyserer **${coinName}/USD** live fra Kraken. Spørg mig om hvad som helst — trend, support/resistance, entry/exit, eller bare "hvad sker der?"`,
      timestamp: new Date(),
    },
  ]);
  const [input, setInput] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [selectedTimeframe, setSelectedTimeframe] = useState("HOUR");
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  // Update welcome message when coin changes
  useEffect(() => {
    const name = selectedCoin.replace("USD", "");
    setMessages([
      {
        id: "welcome",
        role: "assistant",
        content: `Hej! Jeg analyserer **${name}/USD** live fra Kraken. Spørg mig om hvad som helst — trend, support/resistance, entry/exit, eller bare "hvad sker der?"`,
        timestamp: new Date(),
      },
    ]);
  }, [selectedCoin]);

  // Auto-scroll to bottom
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const fetchCandles = useCallback(async (): Promise<ApiCandle[]> => {
    try {
      const resp = await fetch(
        `/api/prices?epic=${selectedCoin}&resolution=${selectedTimeframe}&max=100`
      );
      if (!resp.ok) return [];
      const data = await resp.json();
      return data.candles || [];
    } catch {
      return [];
    }
  }, [selectedCoin, selectedTimeframe]);

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

    try {
      // Fetch fresh candle data for AI context
      const candles = await fetchCandles();

      const resp = await fetch("/api/chart-analysis", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          question: text,
          coin: selectedCoin,
          candles,
          timeframe: selectedTimeframe,
        }),
      });

      let responseText: string;

      if (!resp.ok) {
        const err = await resp.json().catch(() => ({}));
        responseText = err.error === "AI analysis not configured"
          ? "AI-analyse er ikke konfigureret endnu. Sæt ANTHROPIC_API_KEY i Vercel env vars."
          : "Beklager, der opstod en fejl. Prøv igen.";
      } else {
        const data = await resp.json();
        responseText = data.response;
      }

      const aiMsg: Message = {
        id: `ai-${Date.now()}`,
        role: "assistant",
        content: responseText,
        timestamp: new Date(),
      };

      setMessages((prev) => [...prev, aiMsg]);
    } catch {
      setMessages((prev) => [
        ...prev,
        {
          id: `err-${Date.now()}`,
          role: "assistant",
          content: "Netværksfejl. Tjek din forbindelse og prøv igen.",
          timestamp: new Date(),
        },
      ]);
    } finally {
      setIsLoading(false);
      inputRef.current?.focus();
    }
  };

  return (
    <div
      className={cn(
        "rounded-xl border border-border bg-bg-card backdrop-blur-sm shadow-sm flex flex-col",
        className
      )}
    >
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-border">
        <div className="flex items-center gap-2">
          <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-accent-muted">
            <Bot className="h-4 w-4 text-accent" />
          </div>
          <div>
            <h3 className="text-sm font-semibold text-text-primary">AI Chart Analyst</h3>
            <p className="text-xs text-text-muted">
              Analyserer {coinName}/USD
            </p>
          </div>
        </div>

        {/* Timeframe selector for AI context */}
        <div className="flex gap-0.5">
          {[
            { value: "MINUTE_15", label: "15m" },
            { value: "HOUR", label: "1H" },
            { value: "HOUR_4", label: "4H" },
            { value: "DAY", label: "1D" },
          ].map((tf) => (
            <button
              key={tf.value}
              onClick={() => setSelectedTimeframe(tf.value)}
              className={cn(
                "px-1.5 py-0.5 rounded text-[10px] font-medium transition-colors",
                selectedTimeframe === tf.value
                  ? "bg-accent-muted text-accent"
                  : "text-text-muted hover:text-text-secondary"
              )}
            >
              {tf.label}
            </button>
          ))}
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
                  ? "bg-accent-muted text-accent"
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
            <div className="bg-bg-card-hover rounded-lg px-3 py-2 flex items-center gap-2">
              <Loader2 className="h-4 w-4 text-accent animate-spin" />
              <span className="text-xs text-text-muted">Analyserer {coinName}...</span>
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
            placeholder="Hvad sker der med prisen? Skal jeg købe?"
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
