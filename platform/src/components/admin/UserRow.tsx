"use client";

import { useState } from "react";
import {
  ChevronDown,
  ChevronRight,
  Bot,
  ArrowUpDown,
  Shield,
} from "lucide-react";
import { TableRow, TableCell } from "@/components/ui/table";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { createClient } from "@/lib/supabase/client";
import { cn, formatCurrency } from "@/lib/utils";
import type { Profile, Tier, Role, BotInstance, Trade } from "@/lib/supabase/types";

function subscriptionBadge(status: string) {
  switch (status) {
    case "active":
      return <Badge variant="success">Active</Badge>;
    case "past_due":
      return <Badge variant="warning">Past Due</Badge>;
    case "canceled":
      return <Badge variant="danger">Canceled</Badge>;
    case "grace_period":
      return <Badge variant="warning">Grace Period</Badge>;
    default:
      return <Badge variant="outline">None</Badge>;
  }
}

function tierBadge(tier: string | null) {
  switch (tier) {
    case "elite":
      return <Badge variant="default">Elite</Badge>;
    case "pro":
      return <Badge variant="success">Pro</Badge>;
    case "starter":
      return <Badge variant="outline">Starter</Badge>;
    default:
      return <Badge variant="outline">-</Badge>;
  }
}

function roleBadge(role: string) {
  switch (role) {
    case "owner":
      return (
        <Badge variant="default">
          <Shield className="h-3 w-3 mr-1" />
          Owner
        </Badge>
      );
    case "subscriber":
      return <Badge variant="success">Subscriber</Badge>;
    default:
      return <Badge variant="outline">Visitor</Badge>;
  }
}

interface UserRowProps {
  user: Profile;
  bots: BotInstance[];
  trades: Trade[];
}

export default function UserRow({ user, bots, trades }: UserRowProps) {
  const [expanded, setExpanded] = useState(false);
  const [currentTier, setCurrentTier] = useState(user.tier);
  const [currentRole, setCurrentRole] = useState(user.role);
  const [updating, setUpdating] = useState(false);

  async function updateUser(field: string, value: string) {
    setUpdating(true);
    try {
      const supabase = createClient();
      const { error } = await supabase
        .from("profiles")
        .update({ [field]: value })
        .eq("id", user.id);

      if (!error) {
        if (field === "tier") setCurrentTier(value as Tier);
        if (field === "role") setCurrentRole(value as Role);
      }
    } catch {
      // Error handling
    } finally {
      setUpdating(false);
    }
  }

  const totalPL = trades.reduce((sum, t) => sum + (t.profit_loss ?? 0), 0);

  return (
    <>
      <TableRow
        className="cursor-pointer"
        onClick={() => setExpanded(!expanded)}
      >
        <TableCell className="w-8">
          {expanded ? (
            <ChevronDown className="h-4 w-4 text-text-muted" />
          ) : (
            <ChevronRight className="h-4 w-4 text-text-muted" />
          )}
        </TableCell>
        <TableCell className="font-medium">{user.email}</TableCell>
        <TableCell>{user.full_name ?? "-"}</TableCell>
        <TableCell>{roleBadge(currentRole)}</TableCell>
        <TableCell>{tierBadge(currentTier)}</TableCell>
        <TableCell>{subscriptionBadge(user.subscription_status)}</TableCell>
        <TableCell>
          {user.has_2fa ? (
            <Badge variant="success">Yes</Badge>
          ) : (
            <Badge variant="outline">No</Badge>
          )}
        </TableCell>
        <TableCell className="text-text-muted text-xs">
          {new Date(user.created_at).toLocaleDateString("da-DK")}
        </TableCell>
      </TableRow>

      {expanded && (
        <TableRow className="bg-bg-secondary/50">
          <TableCell colSpan={8}>
            <div className="p-4 space-y-4">
              {/* Stats row */}
              <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                <div>
                  <p className="text-xs text-text-muted">Bots</p>
                  <p className="text-lg font-semibold font-mono text-text-primary">
                    {bots.length}
                  </p>
                </div>
                <div>
                  <p className="text-xs text-text-muted">Total Trades</p>
                  <p className="text-lg font-semibold font-mono text-text-primary">
                    {trades.length}
                  </p>
                </div>
                <div>
                  <p className="text-xs text-text-muted">Total P/L</p>
                  <p
                    className={cn(
                      "text-lg font-semibold font-mono",
                      totalPL >= 0 ? "text-success" : "text-danger"
                    )}
                  >
                    {formatCurrency(totalPL)}
                  </p>
                </div>
                <div>
                  <p className="text-xs text-text-muted">User ID</p>
                  <p className="text-xs text-text-muted font-mono truncate">
                    {user.id}
                  </p>
                </div>
              </div>

              {/* Bots list */}
              {bots.length > 0 && (
                <div>
                  <h4 className="text-sm font-medium text-text-primary mb-2 flex items-center gap-1.5">
                    <Bot className="h-4 w-4" /> Bots
                  </h4>
                  <div className="space-y-1">
                    {bots.map((bot) => (
                      <div
                        key={bot.id}
                        className="flex items-center justify-between text-sm bg-bg-card rounded-lg px-3 py-2"
                      >
                        <span className="text-text-primary">{bot.name}</span>
                        <div className="flex items-center gap-2">
                          <Badge
                            variant={
                              bot.status === "running"
                                ? "success"
                                : bot.status === "error"
                                ? "danger"
                                : bot.status === "suspended"
                                ? "warning"
                                : "outline"
                            }
                          >
                            {bot.status}
                          </Badge>
                          <span className="text-xs text-text-muted">
                            {bot.coins.join(", ")}
                          </span>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Actions */}
              <div className="flex flex-wrap items-center gap-2 pt-2 border-t border-border">
                <span className="text-xs text-text-muted mr-2">
                  <ArrowUpDown className="h-3 w-3 inline mr-1" />
                  Actions:
                </span>

                {/* Tier change */}
                <div className="flex items-center gap-1">
                  <span className="text-xs text-text-muted">Tier:</span>
                  {(["starter", "pro", "elite"] as Tier[]).map((t) => (
                    <Button
                      key={t}
                      size="sm"
                      variant={currentTier === t ? "default" : "ghost"}
                      className="h-7 px-2 text-xs"
                      onClick={(e) => {
                        e.stopPropagation();
                        updateUser("tier", t);
                      }}
                      disabled={updating}
                    >
                      {t}
                    </Button>
                  ))}
                </div>

                {/* Role change */}
                <div className="flex items-center gap-1 ml-4">
                  <span className="text-xs text-text-muted">Role:</span>
                  {(["visitor", "subscriber", "owner"] as Role[]).map((r) => (
                    <Button
                      key={r}
                      size="sm"
                      variant={currentRole === r ? "default" : "ghost"}
                      className="h-7 px-2 text-xs"
                      onClick={(e) => {
                        e.stopPropagation();
                        updateUser("role", r);
                      }}
                      disabled={updating}
                    >
                      {r}
                    </Button>
                  ))}
                </div>
              </div>
            </div>
          </TableCell>
        </TableRow>
      )}
    </>
  );
}
