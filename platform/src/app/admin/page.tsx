"use client";

import { useState, useEffect } from "react";
import Link from "next/link";
import {
  Users,
  Bot,
  BarChart3,
  TrendingUp,
  Activity,
  ArrowRight,
} from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Separator } from "@/components/ui/separator";
import { formatCurrency, cn } from "@/lib/utils";
import type { PlatformStats, AuditLog } from "@/lib/supabase/types";

// Mock data
const mockStats: PlatformStats = {
  id: 1,
  total_users: 47,
  active_bots: 23,
  total_trades: 1284,
  total_volume: 892450.0,
  updated_at: new Date().toISOString(),
};

const mockAuditLog: (AuditLog & { actor_email?: string })[] = [
  {
    id: "1",
    actor_id: "u1",
    actor_email: "anton@cryptobot.dk",
    action: "bot.suspended",
    target_type: "bot_instance",
    target_id: "b1",
    details: { reason: "Admin kill switch", bot_name: "BTC Scalper" },
    ip_address: "91.98.26.70",
    created_at: new Date(Date.now() - 1000 * 60 * 5).toISOString(),
  },
  {
    id: "2",
    actor_id: "u2",
    actor_email: "lars@example.com",
    action: "user.login",
    target_type: "user",
    target_id: "u2",
    details: null,
    ip_address: "185.22.10.44",
    created_at: new Date(Date.now() - 1000 * 60 * 12).toISOString(),
  },
  {
    id: "3",
    actor_id: "u3",
    actor_email: "maria@example.com",
    action: "bot.created",
    target_type: "bot_instance",
    target_id: "b3",
    details: { bot_name: "ETH Runner", coins: ["ETHUSD", "SOLUSD"] },
    ip_address: "92.43.87.12",
    created_at: new Date(Date.now() - 1000 * 60 * 25).toISOString(),
  },
  {
    id: "4",
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
    id: "5",
    actor_id: "u5",
    actor_email: "sophie@example.com",
    action: "trade.opened",
    target_type: "trade",
    target_id: "t5",
    details: { epic: "BTCUSD", direction: "BUY", size: 0.5 },
    ip_address: "188.114.22.5",
    created_at: new Date(Date.now() - 1000 * 60 * 60).toISOString(),
  },
  {
    id: "6",
    actor_id: "u2",
    actor_email: "lars@example.com",
    action: "bot.started",
    target_type: "bot_instance",
    target_id: "b6",
    details: { bot_name: "SOL Momentum" },
    ip_address: "185.22.10.44",
    created_at: new Date(Date.now() - 1000 * 60 * 90).toISOString(),
  },
  {
    id: "7",
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
    id: "8",
    actor_id: "u3",
    actor_email: "maria@example.com",
    action: "trade.closed",
    target_type: "trade",
    target_id: "t8",
    details: { epic: "ETHUSD", profit_loss: 42.5 },
    ip_address: "92.43.87.12",
    created_at: new Date(Date.now() - 1000 * 60 * 180).toISOString(),
  },
  {
    id: "9",
    actor_id: "u1",
    actor_email: "anton@cryptobot.dk",
    action: "bot.config_updated",
    target_type: "bot_instance",
    target_id: "b2",
    details: { bot_name: "AVAX Trend", field: "risk_percent", value: 1.5 },
    ip_address: "91.98.26.70",
    created_at: new Date(Date.now() - 1000 * 60 * 240).toISOString(),
  },
  {
    id: "10",
    actor_id: "u4",
    actor_email: "peter@example.com",
    action: "user.2fa_enabled",
    target_type: "user",
    target_id: "u4",
    details: null,
    ip_address: "46.21.155.90",
    created_at: new Date(Date.now() - 1000 * 60 * 300).toISOString(),
  },
];

function actionBadge(action: string) {
  if (action.includes("suspend") || action.includes("error"))
    return <Badge variant="danger">{action}</Badge>;
  if (action.includes("created") || action.includes("started") || action.includes("signup"))
    return <Badge variant="success">{action}</Badge>;
  if (action.includes("changed") || action.includes("updated") || action.includes("config"))
    return <Badge variant="warning">{action}</Badge>;
  return <Badge variant="outline">{action}</Badge>;
}

function timeAgo(dateStr: string): string {
  const diff = Date.now() - new Date(dateStr).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours}h ago`;
  return `${Math.floor(hours / 24)}d ago`;
}

const statCards = [
  {
    label: "Total Users",
    value: mockStats.total_users,
    icon: Users,
    color: "text-accent",
    bgColor: "bg-accent/10",
  },
  {
    label: "Active Bots",
    value: mockStats.active_bots,
    icon: Bot,
    color: "text-success",
    bgColor: "bg-success/10",
  },
  {
    label: "Total Trades",
    value: mockStats.total_trades,
    icon: BarChart3,
    color: "text-warning",
    bgColor: "bg-warning/10",
  },
  {
    label: "Total Volume",
    value: formatCurrency(mockStats.total_volume),
    icon: TrendingUp,
    color: "text-accent",
    bgColor: "bg-accent/10",
    isFormatted: true,
  },
];

export default function AdminOverview() {
  return (
    <div className="space-y-8">
      {/* Stats Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        {statCards.map((stat) => {
          const Icon = stat.icon;
          return (
            <Card key={stat.label}>
              <CardContent className="p-6">
                <div className="flex items-center justify-between">
                  <div>
                    <p className="text-sm text-text-muted">{stat.label}</p>
                    <p className="text-2xl font-bold font-mono text-text-primary mt-1">
                      {stat.isFormatted ? stat.value : stat.value.toLocaleString("da-DK")}
                    </p>
                  </div>
                  <div className={cn("p-3 rounded-lg", stat.bgColor)}>
                    <Icon className={cn("h-5 w-5", stat.color)} />
                  </div>
                </div>
              </CardContent>
            </Card>
          );
        })}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Recent Activity */}
        <div className="lg:col-span-2">
          <Card>
            <CardHeader>
              <div className="flex items-center justify-between">
                <CardTitle className="flex items-center gap-2">
                  <Activity className="h-5 w-5 text-text-muted" />
                  Recent Activity
                </CardTitle>
                <Link href="/admin/audit">
                  <Button variant="ghost" size="sm" className="gap-1">
                    View All <ArrowRight className="h-3.5 w-3.5" />
                  </Button>
                </Link>
              </div>
            </CardHeader>
            <CardContent>
              <div className="space-y-3">
                {mockAuditLog.map((log) => (
                  <div
                    key={log.id}
                    className="flex items-center justify-between py-2"
                  >
                    <div className="flex items-center gap-3 min-w-0">
                      {actionBadge(log.action)}
                      <div className="min-w-0">
                        <p className="text-sm text-text-primary truncate">
                          {log.actor_email}
                        </p>
                        {log.details && (
                          <p className="text-xs text-text-muted truncate">
                            {log.details ? Object.entries(log.details).map(([k, v]) => `${k}: ${v}`).join(" · ") : "-"}
                          </p>
                        )}
                      </div>
                    </div>
                    <span className="text-xs text-text-muted whitespace-nowrap ml-4">
                      {timeAgo(log.created_at)}
                    </span>
                  </div>
                ))}
              </div>
            </CardContent>
          </Card>
        </div>

        {/* Quick Actions */}
        <div>
          <Card>
            <CardHeader>
              <CardTitle>Quick Actions</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              <Link href="/admin/users" className="block">
                <Button variant="outline" className="w-full justify-start gap-2">
                  <Users className="h-4 w-4" />
                  View All Users
                </Button>
              </Link>
              <Link href="/admin/bots" className="block">
                <Button variant="outline" className="w-full justify-start gap-2">
                  <Bot className="h-4 w-4" />
                  View All Bots
                </Button>
              </Link>
              <Link href="/admin/trades" className="block">
                <Button variant="outline" className="w-full justify-start gap-2">
                  <BarChart3 className="h-4 w-4" />
                  View All Trades
                </Button>
              </Link>
              <Separator />
              <div className="pt-1">
                <p className="text-xs text-text-muted mb-2">Platform Health</p>
                <div className="space-y-2">
                  <div className="flex justify-between text-sm">
                    <span className="text-text-secondary">API Status</span>
                    <Badge variant="success">Operational</Badge>
                  </div>
                  <div className="flex justify-between text-sm">
                    <span className="text-text-secondary">DB Connections</span>
                    <span className="text-text-primary font-medium font-mono">12/100</span>
                  </div>
                  <div className="flex justify-between text-sm">
                    <span className="text-text-secondary">Last Updated</span>
                    <span className="text-text-muted text-xs">
                      {new Date(mockStats.updated_at).toLocaleTimeString("da-DK")}
                    </span>
                  </div>
                </div>
              </div>
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  );
}
