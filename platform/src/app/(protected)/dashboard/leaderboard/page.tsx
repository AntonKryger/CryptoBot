"use client";

import { useEffect, useState } from "react";
import { Trophy, ArrowUpDown, ArrowUp, ArrowDown } from "lucide-react";
import { DashboardLayout } from "@/components/layout/DashboardLayout";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { formatCurrency, formatNumber, cn } from "@/lib/utils";

interface LeaderboardEntry {
  bot: string;
  trades: number;
  open: number;
  win_rate: number;
  total_pl: number;
  profit_factor: number;
  sharpe: number;
  max_drawdown: number;
  trades_per_day: number;
  avg_win: number;
  avg_loss: number;
  best_trade: number;
  worst_trade: number;
  composite_score: number;
  rank_tier: "top" | "neutral" | "bottom";
}

type SortKey = keyof LeaderboardEntry;
type BotFilter = "all" | "rule" | "scalp" | "ai";

const FILTER_LABELS: { key: BotFilter; label: string }[] = [
  { key: "all", label: "Alle" },
  { key: "rule", label: "Rule" },
  { key: "scalp", label: "Scalper" },
  { key: "ai", label: "AI" },
];

const COLUMNS: { key: SortKey; label: string; align?: "left" | "right" }[] = [
  { key: "bot", label: "Bot", align: "left" },
  { key: "composite_score", label: "Score" },
  { key: "total_pl", label: "P&L" },
  { key: "win_rate", label: "Win Rate" },
  { key: "profit_factor", label: "PF" },
  { key: "sharpe", label: "Sharpe" },
  { key: "trades", label: "Trades" },
  { key: "trades_per_day", label: "Trades/dag" },
  { key: "max_drawdown", label: "Max DD" },
  { key: "avg_win", label: "Avg Win" },
  { key: "avg_loss", label: "Avg Loss" },
];

function getBotType(bot: string): BotFilter {
  const b = bot.toUpperCase();
  if (/^R[DL]\d/.test(b)) return "rule";
  if (/^S[DL]\d/.test(b)) return "scalp";
  if (/^A[DL]\d/.test(b)) return "ai";
  return "all";
}

function tierBadgeVariant(tier: string) {
  if (tier === "top") return "success" as const;
  if (tier === "bottom") return "danger" as const;
  return "warning" as const;
}

export default function LeaderboardPage() {
  const [data, setData] = useState<LeaderboardEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [filter, setFilter] = useState<BotFilter>("all");
  const [sortKey, setSortKey] = useState<SortKey>("composite_score");
  const [sortAsc, setSortAsc] = useState(false);

  useEffect(() => {
    const controller = new AbortController();
    fetch("/api/leaderboard", { signal: controller.signal })
      .then((r) => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        return r.json();
      })
      .then((d) => {
        setData(Array.isArray(d) ? d : []);
        setLoading(false);
      })
      .catch((e) => {
        if (e.name !== "AbortError") {
          setError(e.message);
          setLoading(false);
        }
      });
    return () => controller.abort();
  }, []);

  function handleSort(key: SortKey) {
    if (sortKey === key) {
      setSortAsc(!sortAsc);
    } else {
      setSortKey(key);
      setSortAsc(key === "bot");
    }
  }

  const filtered =
    filter === "all" ? data : data.filter((e) => getBotType(e.bot) === filter);

  const sorted = [...filtered].sort((a, b) => {
    const va = a[sortKey];
    const vb = b[sortKey];
    if (typeof va === "string" && typeof vb === "string") {
      return sortAsc ? va.localeCompare(vb) : vb.localeCompare(va);
    }
    return sortAsc
      ? (va as number) - (vb as number)
      : (vb as number) - (va as number);
  });

  // Summary KPIs
  const totalBots = filtered.length;
  const avgScore =
    totalBots > 0
      ? filtered.reduce((s, e) => s + e.composite_score, 0) / totalBots
      : 0;
  const totalPl = filtered.reduce((s, e) => s + e.total_pl, 0);
  const topBot =
    filtered.length > 0
      ? [...filtered].sort((a, b) => b.composite_score - a.composite_score)[0]
      : null;

  return (
    <DashboardLayout pageTitle="Leaderboard">
      {/* KPI Cards */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <Card>
          <CardContent className="p-6">
            <div className="flex items-center justify-between">
              <p className="text-sm font-medium text-text-muted">Aktive bots</p>
              <Trophy className="h-[18px] w-[18px] text-accent" />
            </div>
            <p className="mt-2 text-2xl font-bold text-text-primary">
              {loading ? <Skeleton className="h-8 w-16" /> : totalBots}
            </p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="p-6">
            <p className="text-sm font-medium text-text-muted">
              Gns. Composite Score
            </p>
            <p className="mt-2 text-2xl font-bold text-text-primary">
              {loading ? (
                <Skeleton className="h-8 w-16" />
              ) : (
                formatNumber(avgScore)
              )}
            </p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="p-6">
            <p className="text-sm font-medium text-text-muted">Samlet P&L</p>
            <p
              className={cn(
                "mt-2 text-2xl font-bold",
                totalPl >= 0 ? "text-success" : "text-danger"
              )}
            >
              {loading ? (
                <Skeleton className="h-8 w-24" />
              ) : (
                formatCurrency(totalPl)
              )}
            </p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="p-6">
            <p className="text-sm font-medium text-text-muted">Top Bot</p>
            <p className="mt-2 text-2xl font-bold text-accent">
              {loading ? (
                <Skeleton className="h-8 w-20" />
              ) : topBot ? (
                topBot.bot.toUpperCase()
              ) : (
                "-"
              )}
            </p>
            {topBot && !loading && (
              <p className="text-xs text-text-muted mt-1">
                Score: {formatNumber(topBot.composite_score)}
              </p>
            )}
          </CardContent>
        </Card>
      </div>

      {/* Filters */}
      <div className="mt-6 flex gap-2 flex-wrap">
        {FILTER_LABELS.map((f) => (
          <button
            key={f.key}
            onClick={() => setFilter(f.key)}
            className={cn(
              "rounded-lg px-4 py-2 text-sm font-medium transition-colors",
              filter === f.key
                ? "bg-accent text-bg-primary"
                : "bg-bg-card text-text-secondary hover:text-text-primary hover:bg-bg-card-hover border border-border"
            )}
          >
            {f.label}
          </button>
        ))}
      </div>

      {/* Error state */}
      {error && (
        <Card className="mt-6">
          <CardContent className="p-6 text-center text-danger">
            Kunne ikke hente leaderboard: {error}
          </CardContent>
        </Card>
      )}

      {/* Table */}
      <Card className="mt-6">
        <CardHeader>
          <CardTitle>Bot Ranking</CardTitle>
        </CardHeader>
        <CardContent className="p-0">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border">
                  <th className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wider text-text-muted w-10">
                    #
                  </th>
                  {COLUMNS.map((col) => (
                    <th
                      key={col.key}
                      onClick={() => handleSort(col.key)}
                      onKeyDown={(e) => {
                        if (e.key === "Enter" || e.key === " ") {
                          e.preventDefault();
                          handleSort(col.key);
                        }
                      }}
                      role="button"
                      tabIndex={0}
                      aria-sort={
                        sortKey === col.key
                          ? sortAsc
                            ? "ascending"
                            : "descending"
                          : "none"
                      }
                      className={cn(
                        "px-4 py-3 text-xs font-semibold uppercase tracking-wider text-text-muted cursor-pointer hover:text-text-primary transition-colors select-none whitespace-nowrap",
                        col.align === "left" ? "text-left" : "text-right"
                      )}
                    >
                      <span className="inline-flex items-center gap-1">
                        {col.label}
                        {sortKey === col.key ? (
                          sortAsc ? (
                            <ArrowUp className="h-3 w-3" />
                          ) : (
                            <ArrowDown className="h-3 w-3" />
                          )
                        ) : (
                          <ArrowUpDown className="h-3 w-3 opacity-30" />
                        )}
                      </span>
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {loading ? (
                  Array.from({ length: 5 }).map((_, i) => (
                    <tr key={i} className="border-b border-border/50">
                      {Array.from({ length: COLUMNS.length + 1 }).map(
                        (_, j) => (
                          <td key={j} className="px-4 py-3">
                            <Skeleton className="h-5 w-full" />
                          </td>
                        )
                      )}
                    </tr>
                  ))
                ) : sorted.length === 0 ? (
                  <tr>
                    <td
                      colSpan={COLUMNS.length + 1}
                      className="px-4 py-12 text-center text-text-muted"
                    >
                      Ingen data
                    </td>
                  </tr>
                ) : (
                  sorted.map((entry, i) => (
                    <tr
                      key={entry.bot}
                      className={cn(
                        "border-b border-border/50 transition-colors hover:bg-bg-card-hover",
                        entry.rank_tier === "top" &&
                          "border-l-[3px] border-l-success",
                        entry.rank_tier === "bottom" &&
                          "border-l-[3px] border-l-danger"
                      )}
                    >
                      <td className="px-4 py-3 text-text-muted font-mono text-xs">
                        {i + 1}
                      </td>
                      <td className="px-4 py-3 text-left">
                        <span className="font-semibold text-accent">
                          {entry.bot.toUpperCase()}
                        </span>
                      </td>
                      <td className="px-4 py-3 text-right">
                        <Badge variant={tierBadgeVariant(entry.rank_tier)}>
                          {formatNumber(entry.composite_score)}
                        </Badge>
                      </td>
                      <td
                        className={cn(
                          "px-4 py-3 text-right font-medium",
                          entry.total_pl >= 0 ? "text-success" : "text-danger"
                        )}
                      >
                        {formatCurrency(entry.total_pl)}
                      </td>
                      <td className="px-4 py-3 text-right">
                        {formatNumber(entry.win_rate)}%
                      </td>
                      <td className="px-4 py-3 text-right">
                        {formatNumber(entry.profit_factor)}
                      </td>
                      <td className="px-4 py-3 text-right">
                        {formatNumber(entry.sharpe)}
                      </td>
                      <td className="px-4 py-3 text-right font-mono">
                        {entry.trades}
                      </td>
                      <td className="px-4 py-3 text-right">
                        {formatNumber(entry.trades_per_day)}
                      </td>
                      <td className="px-4 py-3 text-right text-danger">
                        {formatCurrency(-Math.abs(entry.max_drawdown))}
                      </td>
                      <td className="px-4 py-3 text-right text-success">
                        {formatCurrency(entry.avg_win)}
                      </td>
                      <td className="px-4 py-3 text-right text-danger">
                        {formatCurrency(entry.avg_loss)}
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </CardContent>
      </Card>
    </DashboardLayout>
  );
}
