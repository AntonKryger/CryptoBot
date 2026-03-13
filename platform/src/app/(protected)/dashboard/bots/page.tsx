"use client";

import { DashboardLayout } from "@/components/layout/DashboardLayout";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import {
  Cpu,
  Play,
  Square,
  Clock,
  Activity,
  Shield,
  TrendingUp,
  Zap,
} from "lucide-react";
import type { BadgeProps } from "@/components/ui/badge";

interface BotInstance {
  id: string;
  name: string;
  status: "running" | "stopped" | "error";
  coins: string[];
  riskPercent: number;
  maxPositions: number;
  activePositions: number;
  uptime: number;
  lastHeartbeat: string;
  totalTrades: number;
  winRate: number;
  totalPnl: number;
  description: string;
}

const mockBots: BotInstance[] = [
  {
    id: "1",
    name: "AI Strategy Bot",
    status: "running",
    coins: ["BTCUSD", "ETHUSD", "SOLUSD", "AVAXUSD", "LINKUSD", "LTCUSD"],
    riskPercent: 1.5,
    maxPositions: 5,
    activePositions: 2,
    uptime: 99.7,
    lastHeartbeat: "2 min ago",
    totalTrades: 147,
    winRate: 67.3,
    totalPnl: 2450.0,
    description: "AI-powered trading with Haiku analysis and hard gate enforcement.",
  },
  {
    id: "2",
    name: "Rule-Based Bot",
    status: "stopped",
    coins: ["BTCUSD", "LINKUSD"],
    riskPercent: 1.0,
    maxPositions: 3,
    activePositions: 0,
    uptime: 94.2,
    lastHeartbeat: "3 hours ago",
    totalTrades: 89,
    winRate: 61.8,
    totalPnl: 890.0,
    description: "EMA crossover and breakout strategy with strict risk management.",
  },
  {
    id: "3",
    name: "Demo Bot",
    status: "error",
    coins: ["BTCUSD", "ETHUSD"],
    riskPercent: 2.0,
    maxPositions: 5,
    activePositions: 0,
    uptime: 45.0,
    lastHeartbeat: "2 days ago",
    totalTrades: 23,
    winRate: 52.2,
    totalPnl: -120.0,
    description: "Paper trading bot for testing strategies without real capital.",
  },
];

const statusConfig: Record<
  BotInstance["status"],
  { label: string; variant: BadgeProps["variant"]; dotClass: string; iconColor: string }
> = {
  running: {
    label: "Running",
    variant: "success",
    dotClass: "bg-success",
    iconColor: "text-success",
  },
  stopped: {
    label: "Stopped",
    variant: "warning",
    dotClass: "bg-warning",
    iconColor: "text-warning",
  },
  error: {
    label: "Error",
    variant: "danger",
    dotClass: "bg-danger",
    iconColor: "text-danger",
  },
};

export default function BotsPage() {
  return (
    <DashboardLayout pageTitle="Bots">
      {/* Overview strip */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 mb-6">
        <div className="rounded-xl border border-border bg-bg-card p-4">
          <p className="text-xs text-text-muted uppercase tracking-wider mb-1">Total Bots</p>
          <p className="text-2xl font-bold font-mono text-text-primary">{mockBots.length}</p>
        </div>
        <div className="rounded-xl border border-border bg-bg-card p-4">
          <p className="text-xs text-text-muted uppercase tracking-wider mb-1">Active</p>
          <p className="text-2xl font-bold font-mono text-success">
            {mockBots.filter((b) => b.status === "running").length}
          </p>
        </div>
        <div className="rounded-xl border border-border bg-bg-card p-4">
          <p className="text-xs text-text-muted uppercase tracking-wider mb-1">Open Positions</p>
          <p className="text-2xl font-bold font-mono text-text-primary">
            {mockBots.reduce((sum, b) => sum + b.activePositions, 0)}
          </p>
        </div>
      </div>

      {/* Bot cards */}
      <div className="grid grid-cols-1 lg:grid-cols-2 xl:grid-cols-3 gap-4">
        {mockBots.map((bot) => {
          const config = statusConfig[bot.status];
          return (
            <div
              key={bot.id}
              className="rounded-xl border border-border bg-bg-card backdrop-blur-sm shadow-sm flex flex-col"
            >
              {/* Card header */}
              <div className="p-6 pb-4">
                <div className="flex items-start justify-between mb-3">
                  <div className="flex items-center gap-3">
                    <div
                      className={cn(
                        "flex h-10 w-10 items-center justify-center rounded-lg",
                        bot.status === "running"
                          ? "bg-success-muted"
                          : bot.status === "error"
                          ? "bg-danger-muted"
                          : "bg-warning-muted"
                      )}
                    >
                      <Cpu className={cn("h-5 w-5", config.iconColor)} />
                    </div>
                    <div>
                      <h3 className="text-sm font-semibold text-text-primary">
                        {bot.name}
                      </h3>
                      <div className="flex items-center gap-1.5 mt-0.5">
                        <span className="relative flex h-2 w-2">
                          {bot.status === "running" && (
                            <span
                              className={cn(
                                "absolute inline-flex h-full w-full animate-ping rounded-full opacity-75",
                                config.dotClass
                              )}
                            />
                          )}
                          <span
                            className={cn(
                              "relative inline-flex h-2 w-2 rounded-full",
                              config.dotClass
                            )}
                          />
                        </span>
                        <Badge variant={config.variant}>{config.label}</Badge>
                      </div>
                    </div>
                  </div>
                </div>

                <p className="text-xs text-text-muted leading-relaxed">
                  {bot.description}
                </p>
              </div>

              {/* Stats grid */}
              <div className="px-6 pb-4 grid grid-cols-2 gap-3">
                <div className="rounded-lg bg-bg-primary/50 p-3">
                  <div className="flex items-center gap-1.5 mb-1">
                    <Activity className="h-3 w-3 text-text-muted" />
                    <span className="text-xs text-text-muted">Uptime</span>
                  </div>
                  <p className="text-sm font-mono font-semibold text-text-primary">
                    {bot.uptime}%
                  </p>
                </div>
                <div className="rounded-lg bg-bg-primary/50 p-3">
                  <div className="flex items-center gap-1.5 mb-1">
                    <Clock className="h-3 w-3 text-text-muted" />
                    <span className="text-xs text-text-muted">Heartbeat</span>
                  </div>
                  <p className="text-sm font-mono font-semibold text-text-primary">
                    {bot.lastHeartbeat}
                  </p>
                </div>
                <div className="rounded-lg bg-bg-primary/50 p-3">
                  <div className="flex items-center gap-1.5 mb-1">
                    <Shield className="h-3 w-3 text-text-muted" />
                    <span className="text-xs text-text-muted">Risk</span>
                  </div>
                  <p className="text-sm font-mono font-semibold text-text-primary">
                    {bot.riskPercent}%
                  </p>
                </div>
                <div className="rounded-lg bg-bg-primary/50 p-3">
                  <div className="flex items-center gap-1.5 mb-1">
                    <TrendingUp className="h-3 w-3 text-text-muted" />
                    <span className="text-xs text-text-muted">Win Rate</span>
                  </div>
                  <p className="text-sm font-mono font-semibold text-text-primary">
                    {bot.winRate}%
                  </p>
                </div>
              </div>

              {/* Positions & trades info */}
              <div className="px-6 pb-4">
                <div className="flex items-center justify-between text-xs mb-2">
                  <span className="text-text-muted">Positions</span>
                  <span className="font-mono text-text-secondary">
                    {bot.activePositions} / {bot.maxPositions}
                  </span>
                </div>
                {/* Position bar */}
                <div className="h-1.5 w-full rounded-full bg-bg-primary/50 overflow-hidden">
                  <div
                    className="h-full rounded-full bg-accent transition-all"
                    style={{
                      width: `${(bot.activePositions / bot.maxPositions) * 100}%`,
                    }}
                  />
                </div>
              </div>

              {/* Coins */}
              <div className="px-6 pb-4">
                <p className="text-xs text-text-muted mb-2">Trading Pairs</p>
                <div className="flex flex-wrap gap-1.5">
                  {bot.coins.map((coin) => (
                    <Badge key={coin} variant="outline">
                      {coin.replace("USD", "")}
                    </Badge>
                  ))}
                </div>
              </div>

              {/* Footer with actions */}
              <div className="mt-auto border-t border-border p-4 flex items-center justify-between">
                <div className="flex items-center gap-1.5">
                  <Zap className="h-3.5 w-3.5 text-text-muted" />
                  <span className="text-xs text-text-muted">
                    {bot.totalTrades} trades
                  </span>
                  <span className="mx-1 text-text-muted">|</span>
                  <span
                    className={cn(
                      "text-xs font-mono font-medium",
                      bot.totalPnl >= 0 ? "text-success" : "text-danger"
                    )}
                  >
                    {bot.totalPnl >= 0 ? "+" : ""}
                    {bot.totalPnl.toFixed(0)} EUR
                  </span>
                </div>
                <div className="flex gap-2">
                  {bot.status === "running" ? (
                    <Button variant="outline" size="sm">
                      <Square className="h-3.5 w-3.5 mr-1.5" />
                      Stop
                    </Button>
                  ) : (
                    <Button variant="default" size="sm">
                      <Play className="h-3.5 w-3.5 mr-1.5" />
                      Start
                    </Button>
                  )}
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </DashboardLayout>
  );
}
