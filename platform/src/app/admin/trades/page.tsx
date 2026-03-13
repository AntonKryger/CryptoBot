"use client";

import { useState, useMemo } from "react";
import {
  BarChart3,
  Search,
  TrendingUp,
  TrendingDown,
  Target,
  Activity,
} from "lucide-react";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import {
  Table,
  TableHeader,
  TableBody,
  TableRow,
  TableHead,
  TableCell,
} from "@/components/ui/table";
import { Button } from "@/components/ui/button";
import { formatCurrency, cn } from "@/lib/utils";
import type { Trade } from "@/lib/supabase/types";

interface TradeWithUser extends Trade {
  user_email: string;
}

const mockTrades: TradeWithUser[] = [
  {
    id: "t1",
    user_id: "u1",
    user_email: "anton@cryptobot.dk",
    bot_instance_id: "b1",
    deal_id: "DEAL001",
    deal_reference: "REF001",
    epic: "BTCUSD",
    direction: "BUY",
    size: 0.5,
    entry_price: 67200,
    exit_price: 67850,
    stop_loss: 66800,
    take_profit: 68000,
    profit_loss: 325.0,
    profit_loss_percent: 2.1,
    status: "closed",
    opened_at: "2026-03-13T06:30:00Z",
    closed_at: "2026-03-13T10:15:00Z",
    signal_mode: "ai_haiku",
    signal_data: null,
    created_at: "2026-03-13T06:30:00Z",
    updated_at: "2026-03-13T10:15:00Z",
  },
  {
    id: "t2",
    user_id: "u2",
    user_email: "lars@example.com",
    bot_instance_id: "b2",
    deal_id: "DEAL002",
    deal_reference: "REF002",
    epic: "SOLUSD",
    direction: "BUY",
    size: 10,
    entry_price: 145.5,
    exit_price: null,
    stop_loss: 140,
    take_profit: 155,
    profit_loss: null,
    profit_loss_percent: null,
    status: "open",
    opened_at: "2026-03-13T07:00:00Z",
    closed_at: null,
    signal_mode: "ema_cross",
    signal_data: null,
    created_at: "2026-03-13T07:00:00Z",
    updated_at: "2026-03-13T07:00:00Z",
  },
  {
    id: "t3",
    user_id: "u5",
    user_email: "sophie@example.com",
    bot_instance_id: "b5",
    deal_id: "DEAL003",
    deal_reference: "REF003",
    epic: "ETHUSD",
    direction: "SELL",
    size: 2,
    entry_price: 3850,
    exit_price: 3780,
    stop_loss: 3900,
    take_profit: 3700,
    profit_loss: 140.0,
    profit_loss_percent: 3.6,
    status: "closed",
    opened_at: "2026-03-13T05:00:00Z",
    closed_at: "2026-03-13T09:30:00Z",
    signal_mode: "ai_haiku",
    signal_data: null,
    created_at: "2026-03-13T05:00:00Z",
    updated_at: "2026-03-13T09:30:00Z",
  },
  {
    id: "t4",
    user_id: "u1",
    user_email: "anton@cryptobot.dk",
    bot_instance_id: "b1",
    deal_id: "DEAL004",
    deal_reference: "REF004",
    epic: "AVAXUSD",
    direction: "BUY",
    size: 50,
    entry_price: 38.2,
    exit_price: 37.5,
    stop_loss: 37.0,
    take_profit: 40.0,
    profit_loss: -35.0,
    profit_loss_percent: -1.8,
    status: "closed",
    opened_at: "2026-03-13T03:00:00Z",
    closed_at: "2026-03-13T04:30:00Z",
    signal_mode: "rsi_divergence",
    signal_data: null,
    created_at: "2026-03-13T03:00:00Z",
    updated_at: "2026-03-13T04:30:00Z",
  },
  {
    id: "t5",
    user_id: "u3",
    user_email: "maria@example.com",
    bot_instance_id: "b3",
    deal_id: "DEAL005",
    deal_reference: "REF005",
    epic: "BTCUSD",
    direction: "SELL",
    size: 0.3,
    entry_price: 67500,
    exit_price: 67200,
    stop_loss: 67800,
    take_profit: 66500,
    profit_loss: 90.0,
    profit_loss_percent: 1.5,
    status: "closed",
    opened_at: "2026-03-12T22:00:00Z",
    closed_at: "2026-03-13T02:00:00Z",
    signal_mode: "macd_cross",
    signal_data: null,
    created_at: "2026-03-12T22:00:00Z",
    updated_at: "2026-03-13T02:00:00Z",
  },
  {
    id: "t6",
    user_id: "u5",
    user_email: "sophie@example.com",
    bot_instance_id: "b5",
    deal_id: "DEAL006",
    deal_reference: "REF006",
    epic: "LINKUSD",
    direction: "BUY",
    size: 100,
    entry_price: 18.5,
    exit_price: null,
    stop_loss: 17.5,
    take_profit: 20.0,
    profit_loss: null,
    profit_loss_percent: null,
    status: "open",
    opened_at: "2026-03-13T08:00:00Z",
    closed_at: null,
    signal_mode: "ai_haiku",
    signal_data: null,
    created_at: "2026-03-13T08:00:00Z",
    updated_at: "2026-03-13T08:00:00Z",
  },
  {
    id: "t7",
    user_id: "u2",
    user_email: "lars@example.com",
    bot_instance_id: "b2",
    deal_id: "DEAL007",
    deal_reference: "REF007",
    epic: "SOLUSD",
    direction: "SELL",
    size: 15,
    entry_price: 148.0,
    exit_price: 150.2,
    stop_loss: 152.0,
    take_profit: 142.0,
    profit_loss: -33.0,
    profit_loss_percent: -1.5,
    status: "closed",
    opened_at: "2026-03-12T18:00:00Z",
    closed_at: "2026-03-12T20:00:00Z",
    signal_mode: "ema_cross",
    signal_data: null,
    created_at: "2026-03-12T18:00:00Z",
    updated_at: "2026-03-12T20:00:00Z",
  },
  {
    id: "t8",
    user_id: "u1",
    user_email: "anton@cryptobot.dk",
    bot_instance_id: "b1",
    deal_id: "DEAL008",
    deal_reference: "REF008",
    epic: "ETHUSD",
    direction: "BUY",
    size: 1,
    entry_price: 3820,
    exit_price: 3890,
    stop_loss: 3780,
    take_profit: 3950,
    profit_loss: 70.0,
    profit_loss_percent: 1.8,
    status: "closed",
    opened_at: "2026-03-12T14:00:00Z",
    closed_at: "2026-03-12T17:00:00Z",
    signal_mode: "ai_haiku",
    signal_data: null,
    created_at: "2026-03-12T14:00:00Z",
    updated_at: "2026-03-12T17:00:00Z",
  },
];

type FilterDirection = "ALL" | "BUY" | "SELL";

const pairs = ["ALL", "BTCUSD", "ETHUSD", "SOLUSD", "AVAXUSD", "LINKUSD", "LTCUSD"];

export default function TradesPage() {
  const [search, setSearch] = useState("");
  const [dirFilter, setDirFilter] = useState<FilterDirection>("ALL");
  const [pairFilter, setPairFilter] = useState("ALL");

  const filteredTrades = useMemo(() => {
    return mockTrades.filter((t) => {
      if (dirFilter !== "ALL" && t.direction !== dirFilter) return false;
      if (pairFilter !== "ALL" && t.epic !== pairFilter) return false;
      if (search) {
        const lower = search.toLowerCase();
        if (
          !t.user_email.toLowerCase().includes(lower) &&
          !t.epic.toLowerCase().includes(lower) &&
          !t.deal_id.toLowerCase().includes(lower)
        )
          return false;
      }
      return true;
    });
  }, [search, dirFilter, pairFilter]);

  // Today stats
  const todayStart = new Date();
  todayStart.setHours(0, 0, 0, 0);
  const todayTrades = mockTrades.filter(
    (t) => new Date(t.opened_at) >= todayStart
  );
  const closedToday = todayTrades.filter((t) => t.status === "closed");
  const totalPLToday = closedToday.reduce(
    (sum, t) => sum + (t.profit_loss ?? 0),
    0
  );
  const winsToday = closedToday.filter((t) => (t.profit_loss ?? 0) > 0).length;
  const winRate =
    closedToday.length > 0 ? (winsToday / closedToday.length) * 100 : 0;

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center gap-2">
        <BarChart3 className="h-5 w-5 text-text-muted" />
        <h2 className="text-lg font-semibold text-text-primary">
          Trade Overview
        </h2>
      </div>

      {/* Summary Stats */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <Card>
          <CardContent className="p-4">
            <div className="flex items-center gap-3">
              <div className="p-2 rounded-lg bg-accent/10">
                <Activity className="h-4 w-4 text-accent" />
              </div>
              <div>
                <p className="text-xs text-text-muted">Trades Today</p>
                <p className="text-xl font-bold font-mono text-text-primary">
                  {todayTrades.length}
                </p>
              </div>
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="p-4">
            <div className="flex items-center gap-3">
              <div
                className={cn(
                  "p-2 rounded-lg",
                  totalPLToday >= 0 ? "bg-success/10" : "bg-danger/10"
                )}
              >
                {totalPLToday >= 0 ? (
                  <TrendingUp className="h-4 w-4 text-success" />
                ) : (
                  <TrendingDown className="h-4 w-4 text-danger" />
                )}
              </div>
              <div>
                <p className="text-xs text-text-muted">P/L Today</p>
                <p
                  className={cn(
                    "text-xl font-bold font-mono",
                    totalPLToday >= 0 ? "text-success" : "text-danger"
                  )}
                >
                  {formatCurrency(totalPLToday)}
                </p>
              </div>
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="p-4">
            <div className="flex items-center gap-3">
              <div className="p-2 rounded-lg bg-success/10">
                <Target className="h-4 w-4 text-success" />
              </div>
              <div>
                <p className="text-xs text-text-muted">Win Rate Today</p>
                <p className="text-xl font-bold font-mono text-text-primary">
                  {winRate.toFixed(1)}%
                </p>
              </div>
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="p-4">
            <div className="flex items-center gap-3">
              <div className="p-2 rounded-lg bg-warning/10">
                <BarChart3 className="h-4 w-4 text-warning" />
              </div>
              <div>
                <p className="text-xs text-text-muted">Open Positions</p>
                <p className="text-xl font-bold font-mono text-text-primary">
                  {mockTrades.filter((t) => t.status === "open").length}
                </p>
              </div>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Filters */}
      <div className="flex flex-col sm:flex-row gap-3 items-start sm:items-center">
        <div className="relative w-full sm:w-64">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-text-muted" />
          <Input
            placeholder="Search user, pair, deal..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="pl-9"
          />
        </div>
        <div className="flex gap-1">
          {(["ALL", "BUY", "SELL"] as FilterDirection[]).map((d) => (
            <Button
              key={d}
              size="sm"
              variant={dirFilter === d ? "default" : "ghost"}
              className="h-8 text-xs"
              onClick={() => setDirFilter(d)}
            >
              {d}
            </Button>
          ))}
        </div>
        <div className="flex gap-1 flex-wrap">
          {pairs.map((p) => (
            <Button
              key={p}
              size="sm"
              variant={pairFilter === p ? "default" : "ghost"}
              className="h-8 text-xs"
              onClick={() => setPairFilter(p)}
            >
              {p === "ALL" ? "All Pairs" : p.replace("USD", "")}
            </Button>
          ))}
        </div>
      </div>

      {/* Table */}
      <div className="rounded-xl border border-border bg-bg-card overflow-hidden">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Time</TableHead>
              <TableHead>User</TableHead>
              <TableHead>Pair</TableHead>
              <TableHead>Direction</TableHead>
              <TableHead className="text-right">Size</TableHead>
              <TableHead className="text-right">Entry</TableHead>
              <TableHead className="text-right">Exit</TableHead>
              <TableHead className="text-right">P/L</TableHead>
              <TableHead>Status</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {filteredTrades.map((trade) => (
              <TableRow key={trade.id}>
                <TableCell className="text-xs text-text-muted whitespace-nowrap">
                  {new Date(trade.opened_at).toLocaleString("da-DK", {
                    month: "short",
                    day: "numeric",
                    hour: "2-digit",
                    minute: "2-digit",
                  })}
                </TableCell>
                <TableCell className="text-sm">{trade.user_email}</TableCell>
                <TableCell>
                  <span className="font-medium text-text-primary">
                    {trade.epic.replace("USD", "")}
                  </span>
                </TableCell>
                <TableCell>
                  <Badge
                    variant={trade.direction === "BUY" ? "success" : "danger"}
                  >
                    {trade.direction}
                  </Badge>
                </TableCell>
                <TableCell className="text-sm font-mono text-right">{trade.size}</TableCell>
                <TableCell className="text-sm font-mono text-right">
                  {trade.entry_price?.toLocaleString("da-DK") ?? "-"}
                </TableCell>
                <TableCell className="text-sm font-mono text-right">
                  {trade.exit_price?.toLocaleString("da-DK") ?? "-"}
                </TableCell>
                <TableCell className="text-right">
                  {trade.profit_loss != null ? (
                    <span
                      className={cn(
                        "font-medium font-mono",
                        trade.profit_loss >= 0 ? "text-success" : "text-danger"
                      )}
                    >
                      {formatCurrency(trade.profit_loss)}
                    </span>
                  ) : (
                    <span className="text-text-muted">-</span>
                  )}
                </TableCell>
                <TableCell>
                  <Badge
                    variant={
                      trade.status === "open"
                        ? "success"
                        : trade.status === "closed"
                        ? "outline"
                        : "warning"
                    }
                  >
                    {trade.status}
                  </Badge>
                </TableCell>
              </TableRow>
            ))}
            {filteredTrades.length === 0 && (
              <TableRow>
                <TableCell
                  colSpan={9}
                  className="text-center py-8 text-text-muted text-sm"
                >
                  No trades found
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      </div>
    </div>
  );
}
