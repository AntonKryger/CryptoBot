"use client";

import { useState, useCallback } from "react";
import { DashboardLayout } from "@/components/layout/DashboardLayout";
import { TradingChart } from "@/components/dashboard/TradingChart";
import { ChartAIChat } from "@/components/dashboard/ChartAIChat";
import { Panel, Group, Separator } from "react-resizable-panels";
import { GripVertical } from "lucide-react";

export default function ChartsPage() {
  const [selectedCoin, setSelectedCoin] = useState("BTCUSD");
  const [selectedTimeframe, setSelectedTimeframe] = useState("HOUR");

  const handleCoinChange = useCallback((epic: string) => {
    setSelectedCoin(epic);
  }, []);

  return (
    <DashboardLayout pageTitle="Live Charts">
      {/* Desktop: resizable side-by-side panels */}
      <div className="hidden xl:block h-[calc(100vh-140px)] min-h-[550px]">
        <Group orientation="horizontal" className="h-full">
          <Panel defaultSize={65} minSize={40}>
            <TradingChart
              className="h-full"
              onCoinChange={handleCoinChange}
            />
          </Panel>

          <Separator className="w-2 flex items-center justify-center group hover:bg-accent/10 transition-colors rounded">
            <GripVertical className="h-4 w-4 text-text-muted group-hover:text-accent transition-colors" />
          </Separator>

          <Panel defaultSize={35} minSize={20}>
            <ChartAIChat
              selectedCoin={selectedCoin}
              selectedTimeframe={selectedTimeframe}
              onTimeframeChange={setSelectedTimeframe}
              className="h-full"
            />
          </Panel>
        </Group>
      </div>

      {/* Mobile: stacked */}
      <div className="xl:hidden space-y-6">
        <TradingChart
          className="min-h-[500px]"
          onCoinChange={handleCoinChange}
        />
        <ChartAIChat
          selectedCoin={selectedCoin}
          selectedTimeframe={selectedTimeframe}
          onTimeframeChange={setSelectedTimeframe}
          className="h-[500px]"
        />
      </div>
    </DashboardLayout>
  );
}
