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
          Real-time data fra Capital.com med AI-analyse
        </p>
      </div>

      {/* Chart + AI Chat layout */}
      <div className="grid grid-cols-1 xl:grid-cols-[1fr_380px] gap-6">
        {/* Main chart */}
        <TradingChart
          className="min-h-[500px]"
          onCoinChange={(epic) => setSelectedCoin(epic)}
        />

        {/* AI Chat sidebar */}
        <ChartAIChat
          selectedCoin={selectedCoin}
          className="h-[500px] xl:h-auto"
        />
      </div>
    </div>
  );
}
