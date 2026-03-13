"use client";

import { useState, useMemo } from "react";
import { Bot as BotIcon, Search, AlertTriangle } from "lucide-react";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Table,
  TableHeader,
  TableBody,
  TableRow,
  TableHead,
  TableCell,
} from "@/components/ui/table";
import KillSwitch from "@/components/admin/KillSwitch";
import type { BotInstance } from "@/lib/supabase/types";

interface BotWithUser extends BotInstance {
  user_email: string;
}

const mockBots: BotWithUser[] = [
  {
    id: "b1",
    user_id: "u1",
    user_email: "anton@cryptobot.dk",
    exchange_account_id: "ea1",
    name: "BTC Scalper",
    status: "running",
    is_suspended: false,
    suspended_reason: null,
    suspended_by: null,
    suspended_at: null,
    coins: ["BTCUSD", "ETHUSD"],
    risk_percent: 1.5,
    max_positions: 3,
    adx_minimum: 20,
    rr_minimum: 2,
    last_heartbeat: new Date(Date.now() - 60000).toISOString(),
    last_signal_at: new Date(Date.now() - 300000).toISOString(),
    uptime_percent: 99.2,
    created_at: "2026-02-01T10:00:00Z",
    updated_at: "2026-03-13T08:00:00Z",
  },
  {
    id: "b2",
    user_id: "u2",
    user_email: "lars@example.com",
    exchange_account_id: "ea2",
    name: "SOL Momentum",
    status: "running",
    is_suspended: false,
    suspended_reason: null,
    suspended_by: null,
    suspended_at: null,
    coins: ["SOLUSD", "AVAXUSD"],
    risk_percent: 1.0,
    max_positions: 2,
    adx_minimum: 20,
    rr_minimum: 2,
    last_heartbeat: new Date(Date.now() - 30000).toISOString(),
    last_signal_at: null,
    uptime_percent: 97.8,
    created_at: "2026-02-10T14:00:00Z",
    updated_at: "2026-03-13T07:00:00Z",
  },
  {
    id: "b3",
    user_id: "u3",
    user_email: "maria@example.com",
    exchange_account_id: "ea3",
    name: "ETH Runner",
    status: "error",
    is_suspended: false,
    suspended_reason: null,
    suspended_by: null,
    suspended_at: null,
    coins: ["ETHUSD"],
    risk_percent: 1.5,
    max_positions: 2,
    adx_minimum: 20,
    rr_minimum: 2,
    last_heartbeat: new Date(Date.now() - 600000).toISOString(),
    last_signal_at: null,
    uptime_percent: 82.1,
    created_at: "2026-03-01T09:00:00Z",
    updated_at: "2026-03-12T22:00:00Z",
  },
  {
    id: "b4",
    user_id: "u4",
    user_email: "peter@example.com",
    exchange_account_id: "ea4",
    name: "LINK Tracker",
    status: "suspended",
    is_suspended: true,
    suspended_reason: "Payment overdue",
    suspended_by: "u1",
    suspended_at: "2026-03-11T10:00:00Z",
    coins: ["LINKUSD"],
    risk_percent: 1.0,
    max_positions: 1,
    adx_minimum: 20,
    rr_minimum: 2,
    last_heartbeat: new Date(Date.now() - 86400000).toISOString(),
    last_signal_at: null,
    uptime_percent: 45.2,
    created_at: "2026-02-28T16:00:00Z",
    updated_at: "2026-03-11T10:00:00Z",
  },
  {
    id: "b5",
    user_id: "u5",
    user_email: "sophie@example.com",
    exchange_account_id: "ea5",
    name: "Multi-Asset Pro",
    status: "running",
    is_suspended: false,
    suspended_reason: null,
    suspended_by: null,
    suspended_at: null,
    coins: ["BTCUSD", "ETHUSD", "SOLUSD", "LINKUSD"],
    risk_percent: 1.0,
    max_positions: 4,
    adx_minimum: 25,
    rr_minimum: 2.5,
    last_heartbeat: new Date(Date.now() - 15000).toISOString(),
    last_signal_at: new Date(Date.now() - 120000).toISOString(),
    uptime_percent: 99.9,
    created_at: "2026-03-01T11:00:00Z",
    updated_at: "2026-03-13T08:00:00Z",
  },
  {
    id: "b6",
    user_id: "u2",
    user_email: "lars@example.com",
    exchange_account_id: "ea2",
    name: "LTC Swing",
    status: "stopped",
    is_suspended: false,
    suspended_reason: null,
    suspended_by: null,
    suspended_at: null,
    coins: ["LTCUSD"],
    risk_percent: 1.5,
    max_positions: 1,
    adx_minimum: 20,
    rr_minimum: 2,
    last_heartbeat: new Date(Date.now() - 3600000).toISOString(),
    last_signal_at: null,
    uptime_percent: 65.4,
    created_at: "2026-03-05T08:00:00Z",
    updated_at: "2026-03-12T20:00:00Z",
  },
];

function statusBadge(status: string) {
  switch (status) {
    case "running":
      return <Badge variant="success">Running</Badge>;
    case "stopped":
      return <Badge variant="outline">Stopped</Badge>;
    case "error":
      return <Badge variant="danger">Error</Badge>;
    case "suspended":
      return <Badge variant="warning">Suspended</Badge>;
    default:
      return <Badge variant="outline">{status}</Badge>;
  }
}

function heartbeatLabel(hb: string | null): string {
  if (!hb) return "Never";
  const diff = Date.now() - new Date(hb).getTime();
  const secs = Math.floor(diff / 1000);
  if (secs < 60) return `${secs}s ago`;
  const mins = Math.floor(secs / 60);
  if (mins < 60) return `${mins}m ago`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours}h ago`;
  return `${Math.floor(hours / 24)}d ago`;
}

export default function BotsPage() {
  const [search, setSearch] = useState("");
  const [bots, setBots] = useState(mockBots);

  const filteredBots = useMemo(() => {
    if (!search) return bots;
    const lower = search.toLowerCase();
    return bots.filter(
      (b) =>
        b.name.toLowerCase().includes(lower) ||
        b.user_email.toLowerCase().includes(lower) ||
        b.coins.some((c) => c.toLowerCase().includes(lower))
    );
  }, [search, bots]);

  const runningCount = bots.filter((b) => b.status === "running").length;
  const errorCount = bots.filter((b) => b.status === "error").length;
  const suspendedCount = bots.filter((b) => b.is_suspended).length;

  function handleStatusChange(botId: string, suspended: boolean) {
    setBots((prev) =>
      prev.map((b) =>
        b.id === botId
          ? {
              ...b,
              is_suspended: suspended,
              status: suspended ? "suspended" : "stopped",
            }
          : b
      )
    );
  }

  function handleSuspendAllForUser(userId: string) {
    setBots((prev) =>
      prev.map((b) =>
        b.user_id === userId
          ? {
              ...b,
              is_suspended: true,
              status: "suspended" as const,
              suspended_reason: "Admin bulk suspend",
              suspended_at: new Date().toISOString(),
            }
          : b
      )
    );
  }

  // Get unique users for bulk actions
  const usersWithMultipleBots = useMemo(() => {
    const counts: Record<string, { email: string; count: number }> = {};
    bots.forEach((b) => {
      if (!counts[b.user_id]) {
        counts[b.user_id] = { email: b.user_email, count: 0 };
      }
      counts[b.user_id].count++;
    });
    return Object.entries(counts).filter(([, v]) => v.count > 1);
  }, [bots]);

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div className="flex items-center gap-2">
          <BotIcon className="h-5 w-5 text-text-muted" />
          <h2 className="text-lg font-semibold text-text-primary">
            Bot Management
          </h2>
          <div className="flex items-center gap-2 ml-2">
            <Badge variant="success">{runningCount} running</Badge>
            {errorCount > 0 && (
              <Badge variant="danger">{errorCount} error</Badge>
            )}
            {suspendedCount > 0 && (
              <Badge variant="warning">{suspendedCount} suspended</Badge>
            )}
          </div>
        </div>
        <div className="relative w-full sm:w-72">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-text-muted" />
          <Input
            placeholder="Search bots, users, coins..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="pl-9"
          />
        </div>
      </div>

      {/* Bulk Actions */}
      {usersWithMultipleBots.length > 0 && (
        <div className="flex flex-wrap gap-2 items-center">
          <span className="text-xs text-text-muted">
            <AlertTriangle className="h-3 w-3 inline mr-1" />
            Bulk suspend all bots for:
          </span>
          {usersWithMultipleBots.map(([userId, info]) => (
            <Button
              key={userId}
              size="sm"
              variant="outline"
              className="h-7 text-xs text-danger border-danger/30 hover:bg-danger/10"
              onClick={() => handleSuspendAllForUser(userId)}
            >
              {info.email} ({info.count} bots)
            </Button>
          ))}
        </div>
      )}

      {/* Table */}
      <div className="rounded-xl border border-border bg-bg-card overflow-hidden">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>User</TableHead>
              <TableHead>Bot Name</TableHead>
              <TableHead>Status</TableHead>
              <TableHead>Coins</TableHead>
              <TableHead>Risk %</TableHead>
              <TableHead>Last Heartbeat</TableHead>
              <TableHead>Uptime</TableHead>
              <TableHead>Actions</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {filteredBots.map((bot) => (
              <TableRow key={bot.id}>
                <TableCell>
                  <span className="text-sm text-text-primary">
                    {bot.user_email}
                  </span>
                </TableCell>
                <TableCell>
                  <span className="font-medium text-text-primary">
                    {bot.name}
                  </span>
                </TableCell>
                <TableCell>{statusBadge(bot.status)}</TableCell>
                <TableCell>
                  <div className="flex flex-wrap gap-1">
                    {bot.coins.map((coin) => (
                      <span
                        key={coin}
                        className="text-xs bg-bg-secondary px-1.5 py-0.5 rounded text-text-secondary"
                      >
                        {coin.replace("USD", "")}
                      </span>
                    ))}
                  </div>
                </TableCell>
                <TableCell>
                  <span className="text-sm text-text-primary">
                    {bot.risk_percent}%
                  </span>
                </TableCell>
                <TableCell>
                  <span className="text-sm text-text-muted">
                    {heartbeatLabel(bot.last_heartbeat)}
                  </span>
                </TableCell>
                <TableCell>
                  <span className="text-sm text-text-primary">
                    {bot.uptime_percent != null
                      ? `${bot.uptime_percent}%`
                      : "-"}
                  </span>
                </TableCell>
                <TableCell>
                  <KillSwitch
                    botId={bot.id}
                    botName={bot.name}
                    isSuspended={bot.is_suspended}
                    onStatusChange={(suspended) =>
                      handleStatusChange(bot.id, suspended)
                    }
                  />
                </TableCell>
              </TableRow>
            ))}
            {filteredBots.length === 0 && (
              <TableRow>
                <td
                  colSpan={8}
                  className="text-center py-8 text-text-muted text-sm"
                >
                  No bots found
                </td>
              </TableRow>
            )}
          </TableBody>
        </Table>
      </div>
    </div>
  );
}
