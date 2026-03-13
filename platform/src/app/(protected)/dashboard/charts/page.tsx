"use client";

import { useState } from "react";
import { DashboardLayout } from "@/components/layout/DashboardLayout";
import { TradingChart } from "@/components/dashboard/TradingChart";
import { ChartAIChat } from "@/components/dashboard/ChartAIChat";

export default function ChartsPage() {
  const [selectedCoin, setSelectedCoin] = useState("BTCUSD");

  return (
    <DashboardLayout pageTitle="Live Charts">
      <div className="space-y-6">
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
    </DashboardLayout>
  );
}
