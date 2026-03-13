"use client";

import { Wallet, TrendingUp, Target, Trophy } from "lucide-react";
import { DashboardLayout } from "@/components/layout/DashboardLayout";
import { PnlCard } from "@/components/dashboard/PnlCard";
import { BalanceChart } from "@/components/dashboard/BalanceChart";
import { BotStatus } from "@/components/dashboard/BotStatus";
import { TradeTable } from "@/components/dashboard/TradeTable";
import { formatCurrency, formatPercent } from "@/lib/utils";

export default function DashboardPage() {
  return (
    <DashboardLayout pageTitle="Dashboard">
      {/* Top row: 4 PnL cards */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <PnlCard
          title="Balance"
          value={formatCurrency(12450)}
          change={24.5}
          icon={Wallet}
        />
        <PnlCard
          title="Today P/L"
          value={formatCurrency(234.5)}
          change={1.92}
          icon={TrendingUp}
        />
        <PnlCard
          title="Open Positions"
          value="2 / 5"
          icon={Target}
        />
        <PnlCard
          title="Win Rate"
          value={formatPercent(67.3)}
          change={3.2}
          icon={Trophy}
        />
      </div>

      {/* Middle row: BalanceChart (2/3) + BotStatus (1/3) */}
      <div className="mt-6 grid grid-cols-1 gap-4 lg:grid-cols-3">
        <div className="lg:col-span-2">
          <BalanceChart />
        </div>
        <div className="lg:col-span-1">
          <BotStatus />
        </div>
      </div>

      {/* Bottom: Recent trades */}
      <div className="mt-6">
        <TradeTable />
      </div>
    </DashboardLayout>
  );
}
