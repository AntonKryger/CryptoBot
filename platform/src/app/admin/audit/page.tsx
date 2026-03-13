"use client";

import { useState, useMemo, useEffect } from "react";
import { FileText, Search, RefreshCw } from "lucide-react";
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
import { cn } from "@/lib/utils";
import type { AuditLog } from "@/lib/supabase/types";

interface AuditLogWithActor extends AuditLog {
  actor_email: string;
}

const mockAuditLogs: AuditLogWithActor[] = [
  {
    id: "a1",
    actor_id: "u1",
    actor_email: "anton@cryptobot.dk",
    action: "bot.suspended",
    target_type: "bot_instance",
    target_id: "b4",
    details: { reason: "Payment overdue", bot_name: "LINK Tracker" },
    ip_address: "91.98.26.70",
    created_at: new Date(Date.now() - 1000 * 60 * 5).toISOString(),
  },
  {
    id: "a2",
    actor_id: "u2",
    actor_email: "lars@example.com",
    action: "user.login",
    target_type: "user",
    target_id: "u2",
    details: { method: "email" },
    ip_address: "185.22.10.44",
    created_at: new Date(Date.now() - 1000 * 60 * 12).toISOString(),
  },
  {
    id: "a3",
    actor_id: "u3",
    actor_email: "maria@example.com",
    action: "bot.created",
    target_type: "bot_instance",
    target_id: "b3",
    details: { bot_name: "ETH Runner", coins: ["ETHUSD"] },
    ip_address: "92.43.87.12",
    created_at: new Date(Date.now() - 1000 * 60 * 25).toISOString(),
  },
  {
    id: "a4",
    actor_id: "u1",
    actor_email: "anton@cryptobot.dk",
    action: "user.tier_changed",
    target_type: "user",
    target_id: "u4",
    details: { from: "starter", to: "pro", user_email: "peter@example.com" },
    ip_address: "91.98.26.70",
    created_at: new Date(Date.now() - 1000 * 60 * 45).toISOString(),
  },
  {
    id: "a5",
    actor_id: "u5",
    actor_email: "sophie@example.com",
    action: "trade.opened",
    target_type: "trade",
    target_id: "t6",
    details: { epic: "LINKUSD", direction: "BUY", size: 100 },
    ip_address: "188.114.22.5",
    created_at: new Date(Date.now() - 1000 * 60 * 60).toISOString(),
  },
  {
    id: "a6",
    actor_id: "u2",
    actor_email: "lars@example.com",
    action: "bot.started",
    target_type: "bot_instance",
    target_id: "b2",
    details: { bot_name: "SOL Momentum" },
    ip_address: "185.22.10.44",
    created_at: new Date(Date.now() - 1000 * 60 * 90).toISOString(),
  },
  {
    id: "a7",
    actor_id: "u6",
    actor_email: "erik@example.com",
    action: "user.signup",
    target_type: "user",
    target_id: "u6",
    details: null,
    ip_address: "95.166.33.78",
    created_at: new Date(Date.now() - 1000 * 60 * 120).toISOString(),
  },
  {
    id: "a8",
    actor_id: "u3",
    actor_email: "maria@example.com",
    action: "trade.closed",
    target_type: "trade",
    target_id: "t3",
    details: { epic: "ETHUSD", profit_loss: 140.0 },
    ip_address: "92.43.87.12",
    created_at: new Date(Date.now() - 1000 * 60 * 180).toISOString(),
  },
  {
    id: "a9",
    actor_id: "u1",
    actor_email: "anton@cryptobot.dk",
    action: "bot.config_updated",
    target_type: "bot_instance",
    target_id: "b1",
    details: { bot_name: "BTC Scalper", field: "risk_percent", value: 1.5 },
    ip_address: "91.98.26.70",
    created_at: new Date(Date.now() - 1000 * 60 * 240).toISOString(),
  },
  {
    id: "a10",
    actor_id: "u4",
    actor_email: "peter@example.com",
    action: "user.2fa_enabled",
    target_type: "user",
    target_id: "u4",
    details: null,
    ip_address: "46.21.155.90",
    created_at: new Date(Date.now() - 1000 * 60 * 300).toISOString(),
  },
  {
    id: "a11",
    actor_id: "u1",
    actor_email: "anton@cryptobot.dk",
    action: "user.role_changed",
    target_type: "user",
    target_id: "u2",
    details: {
      from: "visitor",
      to: "subscriber",
      user_email: "lars@example.com",
    },
    ip_address: "91.98.26.70",
    created_at: new Date(Date.now() - 1000 * 60 * 360).toISOString(),
  },
  {
    id: "a12",
    actor_id: "u5",
    actor_email: "sophie@example.com",
    action: "trade.opened",
    target_type: "trade",
    target_id: "t3",
    details: { epic: "ETHUSD", direction: "SELL", size: 2 },
    ip_address: "188.114.22.5",
    created_at: new Date(Date.now() - 1000 * 60 * 420).toISOString(),
  },
  {
    id: "a13",
    actor_id: "u1",
    actor_email: "anton@cryptobot.dk",
    action: "bot.suspended",
    target_type: "bot_instance",
    target_id: "b3",
    details: { reason: "Excessive errors", bot_name: "ETH Runner" },
    ip_address: "91.98.26.70",
    created_at: new Date(Date.now() - 1000 * 60 * 480).toISOString(),
  },
  {
    id: "a14",
    actor_id: "u1",
    actor_email: "anton@cryptobot.dk",
    action: "bot.reactivated",
    target_type: "bot_instance",
    target_id: "b3",
    details: { bot_name: "ETH Runner" },
    ip_address: "91.98.26.70",
    created_at: new Date(Date.now() - 1000 * 60 * 460).toISOString(),
  },
  {
    id: "a15",
    actor_id: "u7",
    actor_email: "anna@example.com",
    action: "subscription.canceled",
    target_type: "user",
    target_id: "u7",
    details: { tier: "starter" },
    ip_address: "77.241.19.33",
    created_at: new Date(Date.now() - 1000 * 60 * 540).toISOString(),
  },
];

const actionTypes = [
  "ALL",
  "user.login",
  "user.signup",
  "user.tier_changed",
  "user.role_changed",
  "user.2fa_enabled",
  "bot.created",
  "bot.started",
  "bot.suspended",
  "bot.reactivated",
  "bot.config_updated",
  "trade.opened",
  "trade.closed",
  "subscription.canceled",
];

function actionBadge(action: string) {
  if (action.includes("suspend"))
    return <Badge variant="danger">{action}</Badge>;
  if (
    action.includes("created") ||
    action.includes("started") ||
    action.includes("signup") ||
    action.includes("reactivated")
  )
    return <Badge variant="success">{action}</Badge>;
  if (action.includes("changed") || action.includes("updated") || action.includes("config"))
    return <Badge variant="warning">{action}</Badge>;
  if (action.includes("canceled"))
    return <Badge variant="danger">{action}</Badge>;
  return <Badge variant="outline">{action}</Badge>;
}

function formatDetails(details: Record<string, unknown> | null): string {
  if (!details) return "-";
  const parts: string[] = [];
  for (const [key, value] of Object.entries(details)) {
    if (Array.isArray(value)) {
      parts.push(`${key}: ${(value as string[]).join(", ")}`);
    } else {
      parts.push(`${key}: ${value}`);
    }
  }
  return parts.join(" | ");
}

export default function AuditPage() {
  const [search, setSearch] = useState("");
  const [actionFilter, setActionFilter] = useState("ALL");
  const [lastRefresh, setLastRefresh] = useState(new Date());

  // Auto-refresh every 30 seconds
  useEffect(() => {
    const interval = setInterval(() => {
      setLastRefresh(new Date());
      // In production: refetch from Supabase
    }, 30000);
    return () => clearInterval(interval);
  }, []);

  const filteredLogs = useMemo(() => {
    return mockAuditLogs.filter((log) => {
      if (actionFilter !== "ALL" && log.action !== actionFilter) return false;
      if (search) {
        const lower = search.toLowerCase();
        if (
          !log.actor_email.toLowerCase().includes(lower) &&
          !log.action.toLowerCase().includes(lower) &&
          !(log.target_id && log.target_id.toLowerCase().includes(lower))
        )
          return false;
      }
      return true;
    });
  }, [search, actionFilter]);

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div className="flex items-center gap-2">
          <FileText className="h-5 w-5 text-text-muted" />
          <h2 className="text-lg font-semibold text-text-primary">
            Audit Log
          </h2>
          <span className="text-xs text-text-muted">
            Auto-refreshes every 30s
          </span>
        </div>
        <div className="flex items-center gap-2">
          <span className="text-xs text-text-muted">
            Last refresh:{" "}
            {lastRefresh.toLocaleTimeString("da-DK")}
          </span>
          <Button
            size="sm"
            variant="ghost"
            onClick={() => setLastRefresh(new Date())}
            className="h-8"
          >
            <RefreshCw className="h-3.5 w-3.5" />
          </Button>
        </div>
      </div>

      {/* Filters */}
      <div className="flex flex-col sm:flex-row gap-3 items-start sm:items-center">
        <div className="relative w-full sm:w-64">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-text-muted" />
          <Input
            placeholder="Search actor, action..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="pl-9"
          />
        </div>
        <div className="flex gap-1 flex-wrap">
          {actionTypes.slice(0, 8).map((a) => (
            <Button
              key={a}
              size="sm"
              variant={actionFilter === a ? "default" : "ghost"}
              className="h-7 text-xs"
              onClick={() => setActionFilter(a)}
            >
              {a === "ALL" ? "All" : a.split(".")[1]}
            </Button>
          ))}
          {/* More button for remaining filters */}
          <select
            className="h-7 px-2 text-xs rounded-lg border border-border bg-bg-input text-text-primary"
            value={actionFilter}
            onChange={(e) => setActionFilter(e.target.value)}
          >
            <option value="ALL">More...</option>
            {actionTypes.slice(8).map((a) => (
              <option key={a} value={a}>
                {a}
              </option>
            ))}
          </select>
        </div>
      </div>

      {/* Table */}
      <div className="rounded-xl border border-border bg-bg-card overflow-hidden">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Time</TableHead>
              <TableHead>Actor</TableHead>
              <TableHead>Action</TableHead>
              <TableHead>Target</TableHead>
              <TableHead>Details</TableHead>
              <TableHead>IP</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {filteredLogs.map((log) => (
              <TableRow key={log.id}>
                <TableCell className="text-xs text-text-muted whitespace-nowrap">
                  {new Date(log.created_at).toLocaleString("da-DK", {
                    month: "short",
                    day: "numeric",
                    hour: "2-digit",
                    minute: "2-digit",
                    second: "2-digit",
                  })}
                </TableCell>
                <TableCell className="text-sm">{log.actor_email}</TableCell>
                <TableCell>{actionBadge(log.action)}</TableCell>
                <TableCell>
                  <span className="text-xs text-text-muted">
                    {log.target_type && (
                      <span className="text-text-secondary">
                        {log.target_type}
                      </span>
                    )}
                    {log.target_id && (
                      <span className="ml-1 font-mono">{log.target_id}</span>
                    )}
                    {!log.target_type && "-"}
                  </span>
                </TableCell>
                <TableCell>
                  <span className="text-xs text-text-muted max-w-xs truncate block">
                    {formatDetails(log.details)}
                  </span>
                </TableCell>
                <TableCell>
                  <span className="text-xs font-mono text-text-muted">
                    {log.ip_address ?? "-"}
                  </span>
                </TableCell>
              </TableRow>
            ))}
            {filteredLogs.length === 0 && (
              <TableRow>
                <td
                  colSpan={6}
                  className="text-center py-8 text-text-muted text-sm"
                >
                  No audit logs found
                </td>
              </TableRow>
            )}
          </TableBody>
        </Table>
      </div>
    </div>
  );
}
