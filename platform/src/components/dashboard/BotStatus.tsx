"use client";

import { cn } from "@/lib/utils";
import { Badge } from "@/components/ui/badge";
import { Cpu, Clock, Activity } from "lucide-react";
import type { BadgeProps } from "@/components/ui/badge";

interface MockBot {
  id: string;
  name: string;
  status: "running" | "stopped" | "error";
  coins: string[];
  lastHeartbeat: string;
  uptime: string;
}

const mockBots: MockBot[] = [
  {
    id: "1",
    name: "AI Strategy Bot",
    status: "running",
    coins: ["BTCUSD", "ETHUSD", "SOLUSD"],
    lastHeartbeat: "2 min ago",
    uptime: "99.7%",
  },
  {
    id: "2",
    name: "Rule-Based Bot",
    status: "stopped",
    coins: ["BTCUSD", "LINKUSD"],
    lastHeartbeat: "3 hours ago",
    uptime: "94.2%",
  },
];

const statusConfig: Record<
  MockBot["status"],
  { label: string; variant: BadgeProps["variant"]; dotClass: string }
> = {
  running: {
    label: "Running",
    variant: "success",
    dotClass: "bg-success",
  },
  stopped: {
    label: "Stopped",
    variant: "warning",
    dotClass: "bg-warning",
  },
  error: {
    label: "Error",
    variant: "danger",
    dotClass: "bg-danger",
  },
};

export function BotStatus() {
  return (
    <div
      className={cn(
        "rounded-xl border border-border bg-bg-card p-6",
        "backdrop-blur-sm shadow-sm"
      )}
    >
      <div className="mb-6">
        <h3 className="text-lg font-semibold text-text-primary">Bot Status</h3>
        <p className="text-sm text-text-muted">Real-time health</p>
      </div>

      <div className="space-y-4">
        {mockBots.map((bot) => {
          const config = statusConfig[bot.status];
          return (
            <div
              key={bot.id}
              className="rounded-lg border border-border bg-bg-primary/50 p-4"
            >
              {/* Header: name + status */}
              <div className="flex items-center justify-between mb-3">
                <div className="flex items-center gap-2">
                  <Cpu className="h-4 w-4 text-text-muted" />
                  <span className="text-sm font-medium text-text-primary">
                    {bot.name}
                  </span>
                </div>
                <div className="flex items-center gap-2">
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

              {/* Details */}
              <div className="grid grid-cols-2 gap-y-2 text-xs">
                <div className="flex items-center gap-1.5 text-text-muted">
                  <Clock className="h-3 w-3" />
                  <span>Heartbeat</span>
                </div>
                <span className="text-right font-mono text-text-secondary">
                  {bot.lastHeartbeat}
                </span>

                <div className="flex items-center gap-1.5 text-text-muted">
                  <Activity className="h-3 w-3" />
                  <span>Uptime (30d)</span>
                </div>
                <span className="text-right font-mono text-text-secondary">
                  {bot.uptime}
                </span>
              </div>

              {/* Coins */}
              <div className="mt-3 flex flex-wrap gap-1.5">
                {bot.coins.map((coin) => (
                  <Badge key={coin} variant="outline">
                    {coin.replace("USD", "")}
                  </Badge>
                ))}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
