"use client";

import { useState } from "react";
import { TradingChart } from "@/components/dashboard/TradingChart";
import { ChartAIChat } from "@/components/dashboard/ChartAIChat";

export default function ChartsPage() {
  const [selectedCoin, setSelectedCoin] = useState("BTCUSD");

  return (
    <div className="space-y-6">
      {/* Page header */}
      <div>
        <h1 className="text-2xl font-bold text-text-primary">Live Charts</h1>
        <p className="text-sm text-text-muted mt-1">
          Real-time candlestick charts with AI-powered analysis
        </p>
      </div>

      {/* Chart + AI Chat layout */}
      <div className="grid grid-cols-1 xl:grid-cols-[1fr_380px] gap-6">
        {/* Main chart */}
        <TradingChart
          className="min-h-[500px]"
          onPriceUpdate={() => {}}
        />

        {/* AI Chat sidebar */}
        <ChartAIChat
          selectedCoin={selectedCoin}
          className="h-[500px] xl:h-auto"
        />
      </div>

      {/* Quick stats row */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        {[
          { label: "24h Volume", value: "$2.4B", change: "+12.3%" },
          { label: "Market Cap", value: "$1.67T", change: "+1.8%" },
          { label: "BTC Dominance", value: "52.4%", change: "-0.3%" },
          { label: "Fear & Greed", value: "45 (Fear)", change: "" },
        ].map((stat) => (
          <div
            key={stat.label}
            className="rounded-xl border border-border bg-bg-card p-4 backdrop-blur-sm shadow-sm"
          >
            <p className="text-xs text-text-muted">{stat.label}</p>
            <p className="text-lg font-mono font-semibold text-text-primary mt-1">
              {stat.value}
            </p>
            {stat.change && (
              <p
                className={`text-xs font-mono mt-0.5 ${
                  stat.change.startsWith("+")
                    ? "text-success"
                    : stat.change.startsWith("-")
                    ? "text-danger"
                    : "text-text-muted"
                }`}
              >
                {stat.change}
              </p>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
