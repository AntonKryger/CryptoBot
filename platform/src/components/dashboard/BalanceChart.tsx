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

// Mock 30 days of balance data: ~10,000 -> ~12,450 with realistic fluctuations
const mockData = [
  { date: "Feb 10", balance: 10000 },
  { date: "Feb 11", balance: 10120 },
  { date: "Feb 12", balance: 10085 },
  { date: "Feb 13", balance: 10230 },
  { date: "Feb 14", balance: 10310 },
  { date: "Feb 15", balance: 10180 },
  { date: "Feb 16", balance: 10350 },
  { date: "Feb 17", balance: 10420 },
  { date: "Feb 18", balance: 10380 },
  { date: "Feb 19", balance: 10550 },
  { date: "Feb 20", balance: 10690 },
  { date: "Feb 21", balance: 10620 },
  { date: "Feb 22", balance: 10780 },
  { date: "Feb 23", balance: 10850 },
  { date: "Feb 24", balance: 10720 },
  { date: "Feb 25", balance: 10900 },
  { date: "Feb 26", balance: 11050 },
  { date: "Feb 27", balance: 11120 },
  { date: "Feb 28", balance: 10980 },
  { date: "Mar 01", balance: 11200 },
  { date: "Mar 02", balance: 11350 },
  { date: "Mar 03", balance: 11280 },
  { date: "Mar 04", balance: 11450 },
  { date: "Mar 05", balance: 11620 },
  { date: "Mar 06", balance: 11540 },
  { date: "Mar 07", balance: 11780 },
  { date: "Mar 08", balance: 11950 },
  { date: "Mar 09", balance: 12100 },
  { date: "Mar 10", balance: 12250 },
  { date: "Mar 11", balance: 12450 },
];

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
  // Read CSS variable colors at runtime so chart respects theme
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
    // Re-read on theme changes via MutationObserver
    const observer = new MutationObserver(readColors);
    observer.observe(document.documentElement, {
      attributes: true,
      attributeFilter: ["data-theme"],
    });
    return () => observer.disconnect();
  }, []);

  return (
    <div
      className={cn(
        "rounded-xl border border-border bg-bg-card p-6",
        "backdrop-blur-sm shadow-sm"
      )}
    >
      <div className="mb-6">
        <h3 className="text-lg font-semibold text-text-primary">
          Balance History
        </h3>
        <p className="text-sm text-text-muted">Last 30 days</p>
      </div>

      <div className="h-[300px]">
        <ResponsiveContainer width="100%" height="100%">
          <AreaChart
            data={mockData}
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
              tick={{ fill: labelColor, fontSize: 12 }}
              tickLine={false}
              axisLine={false}
              interval={4}
            />
            <YAxis
              tick={{ fill: labelColor, fontSize: 12 }}
              tickLine={false}
              axisLine={false}
              tickFormatter={(v) => `${(v / 1000).toFixed(0)}k`}
              width={45}
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
      </div>
    </div>
  );
}
