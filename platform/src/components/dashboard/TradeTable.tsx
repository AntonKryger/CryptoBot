"use client";

import { cn } from "@/lib/utils";
import { formatCurrency } from "@/lib/utils";
import { Badge } from "@/components/ui/badge";
import {
  Table,
  TableHeader,
  TableBody,
  TableRow,
  TableHead,
  TableCell,
} from "@/components/ui/table";

interface Trade {
  id: string;
  date: string;
  pair: string;
  direction: "BUY" | "SELL";
  entry: number;
  exit: number | null;
  pnl: number;
  status: "Closed" | "Open";
}

const mockTrades: Trade[] = [
  {
    id: "1",
    date: "2026-03-11 14:32",
    pair: "BTCUSD",
    direction: "BUY",
    entry: 71250.5,
    exit: 71890.0,
    pnl: 382.5,
    status: "Closed",
  },
  {
    id: "2",
    date: "2026-03-11 09:15",
    pair: "ETHUSD",
    direction: "BUY",
    entry: 3845.2,
    exit: null,
    pnl: 124.8,
    status: "Open",
  },
  {
    id: "3",
    date: "2026-03-10 22:05",
    pair: "SOLUSD",
    direction: "SELL",
    entry: 148.35,
    exit: 145.1,
    pnl: 195.0,
    status: "Closed",
  },
  {
    id: "4",
    date: "2026-03-10 16:48",
    pair: "BTCUSD",
    direction: "BUY",
    entry: 70980.0,
    exit: 70650.0,
    pnl: -198.0,
    status: "Closed",
  },
  {
    id: "5",
    date: "2026-03-10 11:22",
    pair: "LINKUSD",
    direction: "BUY",
    entry: 18.45,
    exit: 19.12,
    pnl: 67.0,
    status: "Closed",
  },
  {
    id: "6",
    date: "2026-03-09 20:10",
    pair: "AVAXUSD",
    direction: "SELL",
    entry: 42.8,
    exit: 43.5,
    pnl: -105.0,
    status: "Closed",
  },
  {
    id: "7",
    date: "2026-03-09 13:55",
    pair: "ETHUSD",
    direction: "BUY",
    entry: 3790.0,
    exit: null,
    pnl: 89.3,
    status: "Open",
  },
  {
    id: "8",
    date: "2026-03-09 08:30",
    pair: "LTCUSD",
    direction: "BUY",
    entry: 98.5,
    exit: 101.2,
    pnl: 135.0,
    status: "Closed",
  },
];

export function TradeTable() {
  return (
    <div
      className={cn(
        "rounded-xl border border-border bg-bg-card",
        "backdrop-blur-sm shadow-sm"
      )}
    >
      <div className="flex items-center justify-between p-6 pb-4">
        <div>
          <h3 className="text-lg font-semibold text-text-primary">
            Recent Trades
          </h3>
          <p className="text-sm text-text-muted">Last 8 trades</p>
        </div>
        <a
          href="/dashboard/trades"
          className="text-sm font-medium text-accent hover:text-accent/80 transition-colors"
        >
          View All &rarr;
        </a>
      </div>

      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Date</TableHead>
            <TableHead>Pair</TableHead>
            <TableHead>Direction</TableHead>
            <TableHead className="text-right">Entry</TableHead>
            <TableHead className="text-right">Exit</TableHead>
            <TableHead className="text-right">P/L</TableHead>
            <TableHead className="text-right">Status</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {mockTrades.map((trade) => (
            <TableRow key={trade.id}>
              <TableCell className="font-mono text-sm text-text-secondary">
                {trade.date}
              </TableCell>
              <TableCell className="font-medium text-text-primary">
                {trade.pair}
              </TableCell>
              <TableCell>
                <Badge
                  variant={trade.direction === "BUY" ? "success" : "danger"}
                >
                  {trade.direction}
                </Badge>
              </TableCell>
              <TableCell className="text-right font-mono">
                {trade.entry.toLocaleString("da-DK", {
                  minimumFractionDigits: 2,
                })}
              </TableCell>
              <TableCell className="text-right font-mono text-text-secondary">
                {trade.exit
                  ? trade.exit.toLocaleString("da-DK", {
                      minimumFractionDigits: 2,
                    })
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
              <TableCell className="text-right">
                <Badge
                  variant={trade.status === "Open" ? "warning" : "outline"}
                >
                  {trade.status}
                </Badge>
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}
