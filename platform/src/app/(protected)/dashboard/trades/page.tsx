"use client";

import { useState } from "react";
import { DashboardLayout } from "@/components/layout/DashboardLayout";
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
import { formatCurrency } from "@/lib/utils";
import { Search, Filter, Download } from "lucide-react";

interface Trade {
  id: string;
  date: string;
  pair: string;
  direction: "BUY" | "SELL";
  size: number;
  entry: number;
  exit: number | null;
  pnl: number;
  status: "open" | "closed" | "canceled";
  signalMode: string;
}

const allTrades: Trade[] = [
  { id: "1", date: "2026-03-11 14:32", pair: "BTCUSD", direction: "BUY", size: 0.05, entry: 71250.5, exit: 71890.0, pnl: 382.5, status: "closed", signalMode: "AI Trend" },
  { id: "2", date: "2026-03-11 09:15", pair: "ETHUSD", direction: "BUY", size: 0.8, entry: 3845.2, exit: null, pnl: 124.8, status: "open", signalMode: "AI Momentum" },
  { id: "3", date: "2026-03-10 22:05", pair: "SOLUSD", direction: "SELL", size: 5.0, entry: 148.35, exit: 145.1, pnl: 195.0, status: "closed", signalMode: "Rule EMA" },
  { id: "4", date: "2026-03-10 16:48", pair: "BTCUSD", direction: "BUY", size: 0.03, entry: 70980.0, exit: 70650.0, pnl: -198.0, status: "closed", signalMode: "AI Trend" },
  { id: "5", date: "2026-03-10 11:22", pair: "LINKUSD", direction: "BUY", size: 20.0, entry: 18.45, exit: 19.12, pnl: 67.0, status: "closed", signalMode: "Rule Breakout" },
  { id: "6", date: "2026-03-09 20:10", pair: "AVAXUSD", direction: "SELL", size: 10.0, entry: 42.8, exit: 43.5, pnl: -105.0, status: "closed", signalMode: "AI Reversal" },
  { id: "7", date: "2026-03-09 13:55", pair: "ETHUSD", direction: "BUY", size: 0.5, entry: 3790.0, exit: null, pnl: 89.3, status: "open", signalMode: "Rule EMA" },
  { id: "8", date: "2026-03-09 08:30", pair: "LTCUSD", direction: "BUY", size: 3.0, entry: 98.5, exit: 101.2, pnl: 135.0, status: "closed", signalMode: "AI Trend" },
  { id: "9", date: "2026-03-08 19:45", pair: "BTCUSD", direction: "SELL", size: 0.04, entry: 71500.0, exit: 71100.0, pnl: 240.0, status: "closed", signalMode: "AI Momentum" },
  { id: "10", date: "2026-03-08 14:20", pair: "SOLUSD", direction: "BUY", size: 8.0, entry: 145.0, exit: 147.8, pnl: 224.0, status: "closed", signalMode: "Rule Breakout" },
  { id: "11", date: "2026-03-08 09:00", pair: "ETHUSD", direction: "SELL", size: 1.0, entry: 3900.0, exit: 3870.0, pnl: 30.0, status: "closed", signalMode: "AI Reversal" },
  { id: "12", date: "2026-03-07 21:30", pair: "LINKUSD", direction: "BUY", size: 15.0, entry: 17.9, exit: 17.5, pnl: -60.0, status: "closed", signalMode: "Rule EMA" },
  { id: "13", date: "2026-03-07 16:10", pair: "BTCUSD", direction: "BUY", size: 0.06, entry: 70200.0, exit: 70850.0, pnl: 390.0, status: "closed", signalMode: "AI Trend" },
  { id: "14", date: "2026-03-07 10:45", pair: "AVAXUSD", direction: "BUY", size: 12.0, entry: 41.5, exit: 42.3, pnl: 96.0, status: "closed", signalMode: "Rule Breakout" },
  { id: "15", date: "2026-03-06 22:00", pair: "LTCUSD", direction: "SELL", size: 4.0, entry: 100.0, exit: 97.8, pnl: 88.0, status: "closed", signalMode: "AI Momentum" },
  { id: "16", date: "2026-03-06 15:30", pair: "SOLUSD", direction: "BUY", size: 6.0, entry: 142.0, exit: null, pnl: -45.0, status: "canceled", signalMode: "Rule EMA" },
];

const PAIRS = ["All", "BTCUSD", "ETHUSD", "SOLUSD", "AVAXUSD", "LINKUSD", "LTCUSD"];
const DIRECTIONS = ["All", "BUY", "SELL"];
const STATUSES = ["All", "open", "closed", "canceled"];

export default function TradesPage() {
  const [pairFilter, setPairFilter] = useState("All");
  const [dirFilter, setDirFilter] = useState("All");
  const [statusFilter, setStatusFilter] = useState("All");
  const [showFilters, setShowFilters] = useState(false);

  const filtered = allTrades.filter((t) => {
    if (pairFilter !== "All" && t.pair !== pairFilter) return false;
    if (dirFilter !== "All" && t.direction !== dirFilter) return false;
    if (statusFilter !== "All" && t.status !== statusFilter) return false;
    return true;
  });

  const totalPnl = filtered.reduce((sum, t) => sum + t.pnl, 0);
  const winCount = filtered.filter((t) => t.pnl > 0).length;
  const winRate = filtered.length > 0 ? (winCount / filtered.length) * 100 : 0;

  return (
    <DashboardLayout pageTitle="Trades">
      {/* Summary strip */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 mb-6">
        <div className="rounded-xl border border-border bg-bg-card p-4">
          <p className="text-xs text-text-muted uppercase tracking-wider mb-1">Total Trades</p>
          <p className="text-2xl font-bold font-mono text-text-primary">{filtered.length}</p>
        </div>
        <div className="rounded-xl border border-border bg-bg-card p-4">
          <p className="text-xs text-text-muted uppercase tracking-wider mb-1">Net P/L</p>
          <p className={cn("text-2xl font-bold font-mono", totalPnl >= 0 ? "text-success" : "text-danger")}>
            {totalPnl >= 0 ? "+" : ""}{formatCurrency(totalPnl)}
          </p>
        </div>
        <div className="rounded-xl border border-border bg-bg-card p-4">
          <p className="text-xs text-text-muted uppercase tracking-wider mb-1">Win Rate</p>
          <p className="text-2xl font-bold font-mono text-text-primary">{winRate.toFixed(1)}%</p>
        </div>
      </div>

      {/* Toolbar */}
      <div className="flex flex-wrap items-center gap-2 mb-4">
        <Button
          variant="outline"
          size="sm"
          onClick={() => setShowFilters(!showFilters)}
        >
          <Filter className="h-4 w-4 mr-2" />
          Filters
          {(pairFilter !== "All" || dirFilter !== "All" || statusFilter !== "All") && (
            <span className="ml-2 flex h-5 w-5 items-center justify-center rounded-full bg-accent text-white text-xs">
              {[pairFilter, dirFilter, statusFilter].filter(f => f !== "All").length}
            </span>
          )}
        </Button>
        <Button variant="outline" size="sm">
          <Download className="h-4 w-4 mr-2" />
          Export CSV
        </Button>
      </div>

      {/* Filter bar */}
      {showFilters && (
        <div className="flex flex-wrap items-center gap-4 mb-4 p-4 rounded-lg border border-border bg-bg-card animate-fade-in">
          <div>
            <label className="block text-xs text-text-muted mb-1">Pair</label>
            <select
              value={pairFilter}
              onChange={(e) => setPairFilter(e.target.value)}
              className="h-9 rounded-lg border border-border bg-bg-input px-3 text-sm text-text-primary focus:outline-none focus:ring-2 focus:ring-accent"
            >
              {PAIRS.map((p) => (
                <option key={p} value={p}>{p}</option>
              ))}
            </select>
          </div>
          <div>
            <label className="block text-xs text-text-muted mb-1">Direction</label>
            <select
              value={dirFilter}
              onChange={(e) => setDirFilter(e.target.value)}
              className="h-9 rounded-lg border border-border bg-bg-input px-3 text-sm text-text-primary focus:outline-none focus:ring-2 focus:ring-accent"
            >
              {DIRECTIONS.map((d) => (
                <option key={d} value={d}>{d}</option>
              ))}
            </select>
          </div>
          <div>
            <label className="block text-xs text-text-muted mb-1">Status</label>
            <select
              value={statusFilter}
              onChange={(e) => setStatusFilter(e.target.value)}
              className="h-9 rounded-lg border border-border bg-bg-input px-3 text-sm text-text-primary focus:outline-none focus:ring-2 focus:ring-accent"
            >
              {STATUSES.map((s) => (
                <option key={s} value={s}>{s === "All" ? "All" : s.charAt(0).toUpperCase() + s.slice(1)}</option>
              ))}
            </select>
          </div>
          <div className="flex items-end">
            <Button
              variant="ghost"
              size="sm"
              onClick={() => {
                setPairFilter("All");
                setDirFilter("All");
                setStatusFilter("All");
              }}
            >
              Clear
            </Button>
          </div>
        </div>
      )}

      {/* Trade table */}
      <div className="rounded-xl border border-border bg-bg-card backdrop-blur-sm shadow-sm">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Time</TableHead>
              <TableHead>Pair</TableHead>
              <TableHead>Direction</TableHead>
              <TableHead className="text-right">Size</TableHead>
              <TableHead className="text-right">Entry</TableHead>
              <TableHead className="text-right">Exit</TableHead>
              <TableHead className="text-right">P/L</TableHead>
              <TableHead>Signal</TableHead>
              <TableHead className="text-right">Status</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {filtered.length === 0 ? (
              <TableRow>
                <TableCell colSpan={9} className="text-center py-8 text-text-muted">
                  No trades match the current filters.
                </TableCell>
              </TableRow>
            ) : (
              filtered.map((trade) => (
                <TableRow key={trade.id}>
                  <TableCell className="font-mono text-sm text-text-secondary whitespace-nowrap">
                    {trade.date}
                  </TableCell>
                  <TableCell className="font-medium text-text-primary">
                    {trade.pair}
                  </TableCell>
                  <TableCell>
                    <Badge variant={trade.direction === "BUY" ? "success" : "danger"}>
                      {trade.direction}
                    </Badge>
                  </TableCell>
                  <TableCell className="text-right font-mono">
                    {trade.size}
                  </TableCell>
                  <TableCell className="text-right font-mono">
                    {trade.entry.toLocaleString("da-DK", { minimumFractionDigits: 2 })}
                  </TableCell>
                  <TableCell className="text-right font-mono text-text-secondary">
                    {trade.exit
                      ? trade.exit.toLocaleString("da-DK", { minimumFractionDigits: 2 })
                      : "\u2014"}
                  </TableCell>
                  <TableCell
                    className={cn(
                      "text-right font-mono font-medium",
                      trade.pnl >= 0 ? "text-success" : "text-danger"
                    )}
                  >
                    {trade.pnl >= 0 ? "+" : ""}
                    {formatCurrency(trade.pnl)}
                  </TableCell>
                  <TableCell>
                    <span className="text-xs text-text-muted">{trade.signalMode}</span>
                  </TableCell>
                  <TableCell className="text-right">
                    <Badge
                      variant={
                        trade.status === "open"
                          ? "warning"
                          : trade.status === "canceled"
                          ? "danger"
                          : "outline"
                      }
                    >
                      {trade.status.charAt(0).toUpperCase() + trade.status.slice(1)}
                    </Badge>
                  </TableCell>
                </TableRow>
              ))
            )}
          </TableBody>
        </Table>
      </div>
    </DashboardLayout>
  );
}
