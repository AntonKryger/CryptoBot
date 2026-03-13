"use client";

import { cn } from "@/lib/utils";
import { formatPercent } from "@/lib/utils";
import type { LucideIcon } from "lucide-react";

interface PnlCardProps {
  title: string;
  value: string;
  change?: number;
  icon: LucideIcon;
}

export function PnlCard({ title, value, change, icon: Icon }: PnlCardProps) {
  const isPositive = change !== undefined && change >= 0;
  const isNegative = change !== undefined && change < 0;

  return (
    <div
      className={cn(
        "rounded-xl border border-border bg-bg-card p-6",
        "backdrop-blur-sm shadow-sm"
      )}
    >
      <div className="flex items-center justify-between">
        <p className="text-sm font-medium text-text-muted">{title}</p>
        <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-accent-muted">
          <Icon className="h-[18px] w-[18px] text-accent" />
        </div>
      </div>

      <div className="mt-3 flex items-end gap-3">
        <p className="text-2xl font-bold font-mono text-text-primary">
          {value}
        </p>
        {change !== undefined && (
          <span
            className={cn(
              "inline-flex items-center rounded-md px-2 py-0.5 text-xs font-medium",
              isPositive && "bg-success-muted text-success",
              isNegative && "bg-danger-muted text-danger"
            )}
          >
            {formatPercent(change)}
          </span>
        )}
      </div>
    </div>
  );
}
