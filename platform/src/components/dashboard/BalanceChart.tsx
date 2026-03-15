"use client";

import { useEffect, useState } from "react";
import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from "recharts";
import { cn } from "@/lib/utils";
import { formatCurrency } from "@/lib/utils";
import { createClient } from "@/lib/supabase/client";

interface ChartPoint {
  date: string;
  balance: number;
}

interface CustomTooltipProps {
  active?: boolean;
  payload?: Array<{ value: number }>;
  label?: string;
}

function CustomTooltip({ active, payload, label }: CustomTooltipProps) {
  if (!active || !payload?.length) return null;
  return (
    <div className="rounded-lg border border-border bg-bg-card px-3 py-2 shadow-lg">
      <p className="text-xs text-text-muted">{label}</p>
      <p className="text-sm font-mono font-semibold text-text-primary">
        {formatCurrency(payload[0].value)}
      </p>
    </div>
  );
}

export function BalanceChart() {
  const [data, setData] = useState<ChartPoint[]>([]);
  const [chartColor, setChartColor] = useState("#6366f1");
  const [gridColor, setGridColor] = useState("#2a3150");
  const [labelColor, setLabelColor] = useState("#64748b");

  useEffect(() => {
    function readColors() {
      const style = getComputedStyle(document.documentElement);
      setChartColor(style.getPropertyValue("--chart-1").trim() || "#6366f1");
      setGridColor(style.getPropertyValue("--border").trim() || "#2a3150");
      setLabelColor(style.getPropertyValue("--text-muted").trim() || "#64748b");
    }
    readColors();
    const observer = new MutationObserver(readColors);
    observer.observe(document.documentElement, {
      attributes: true,
      attributeFilter: ["data-theme"],
    });
    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    async function load() {
      const supabase = createClient();

      // Last 7 days of equity snapshots
      const since = new Date();
      since.setDate(since.getDate() - 7);

      const { data: rows } = await supabase
        .from("equity_snapshots")
        .select("equity, snapshot_at")
        .gte("snapshot_at", since.toISOString())
        .order("snapshot_at", { ascending: true });

      if (!rows || rows.length === 0) return;

      // Aggregate: take last snapshot per hour across all bots (sum equity per timestamp bucket)
      // Group by hour, sum equity per distinct bot within each hour, take latest per bot
      const buckets = new Map<string, Map<string, number>>();

      for (const row of rows) {
        const dt = new Date(row.snapshot_at);
        // Bucket key: date + hour
        const key = `${dt.toISOString().slice(0, 13)}`;
        if (!buckets.has(key)) buckets.set(key, new Map());
        // For aggregation across bots sharing same account, just use latest equity value per bucket
        // Since all 4 bots report the same Kraken account equity, take the max (most recent)
        const bucket = buckets.get(key)!;
        const current = bucket.get("equity") ?? 0;
        const val = Number(row.equity);
        if (val > current) bucket.set("equity", val);
      }

      const points: ChartPoint[] = [];
      Array.from(buckets.entries()).forEach(([key, bucket]) => {
        const dt = new Date(key + ":00:00.000Z");
        points.push({
          date: dt.toLocaleDateString("da-DK", { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" }),
          balance: bucket.get("equity") ?? 0,
        });
      });

      // Deduplicate to max ~50 points for readability
      if (points.length > 50) {
        const step = Math.ceil(points.length / 50);
        const sampled = points.filter((_, i) => i % step === 0 || i === points.length - 1);
        setData(sampled);
      } else {
        setData(points);
      }
    }
    load();
  }, []);

  const hasData = data.length > 0;

  // Compute Y-axis domain with padding
  const minVal = hasData ? Math.min(...data.map((d) => d.balance)) : 0;
  const maxVal = hasData ? Math.max(...data.map((d) => d.balance)) : 1000;
  const padding = (maxVal - minVal) * 0.1 || 10;

  return (
    <div
      className={cn(
        "rounded-xl border border-border bg-bg-card p-6",
        "backdrop-blur-sm shadow-sm"
      )}
    >
      <div className="mb-6">
        <h3 className="text-lg font-semibold text-text-primary">
          Equity History
        </h3>
        <p className="text-sm text-text-muted">
          {hasData ? "Last 7 days" : "Waiting for equity data from bots..."}
        </p>
      </div>

      <div className="h-[300px]">
        {hasData ? (
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart
              data={data}
              margin={{ top: 5, right: 5, left: 10, bottom: 5 }}
            >
              <defs>
                <linearGradient id="balanceGradient" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor={chartColor} stopOpacity={0.3} />
                  <stop offset="100%" stopColor={chartColor} stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid
                strokeDasharray="3 3"
                stroke={gridColor}
                vertical={false}
              />
              <XAxis
                dataKey="date"
                tick={{ fill: labelColor, fontSize: 11 }}
                tickLine={false}
                axisLine={false}
                interval={Math.max(0, Math.floor(data.length / 6) - 1)}
              />
              <YAxis
                tick={{ fill: labelColor, fontSize: 12 }}
                tickLine={false}
                axisLine={false}
                domain={[minVal - padding, maxVal + padding]}
                tickFormatter={(v) =>
                  v >= 1000 ? `$${(v / 1000).toFixed(1)}k` : `$${v.toFixed(0)}`
                }
                width={55}
              />
              <Tooltip content={<CustomTooltip />} />
              <Area
                type="monotone"
                dataKey="balance"
                stroke={chartColor}
                strokeWidth={2}
                fill="url(#balanceGradient)"
              />
            </AreaChart>
          </ResponsiveContainer>
        ) : (
          <div className="h-full flex items-center justify-center text-text-muted text-sm">
            Chart will appear when bots start sending equity snapshots.
          </div>
        )}
      </div>
    </div>
  );
}
