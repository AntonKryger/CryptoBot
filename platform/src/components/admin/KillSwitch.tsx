"use client";

import { useState } from "react";
import { Shield, AlertTriangle } from "lucide-react";
import { Button } from "@/components/ui/button";
import { createClient } from "@/lib/supabase/client";
import { cn } from "@/lib/utils";

interface KillSwitchProps {
  botId: string;
  botName: string;
  isSuspended: boolean;
  onStatusChange?: (suspended: boolean) => void;
}

export default function KillSwitch({
  botId,
  botName,
  isSuspended,
  onStatusChange,
}: KillSwitchProps) {
  const [confirming, setConfirming] = useState(false);
  const [loading, setLoading] = useState(false);

  async function handleSuspend() {
    if (!confirming) {
      setConfirming(true);
      return;
    }

    setLoading(true);
    try {
      const supabase = createClient();
      const {
        data: { user },
      } = await supabase.auth.getUser();

      if (!user) return;

      const { error } = await supabase
        .from("bot_instances")
        .update({
          is_suspended: !isSuspended,
          suspended_reason: isSuspended ? null : "Admin kill switch",
          suspended_by: isSuspended ? null : user.id,
          suspended_at: isSuspended ? null : new Date().toISOString(),
          status: isSuspended ? "stopped" : "suspended",
        })
        .eq("id", botId);

      if (!error) {
        onStatusChange?.(!isSuspended);
      }
    } catch {
      // Error handling in production
    } finally {
      setLoading(false);
      setConfirming(false);
    }
  }

  function handleCancel() {
    setConfirming(false);
  }

  if (confirming) {
    return (
      <div className="flex items-center gap-2">
        <span className="text-xs text-danger font-medium">
          {isSuspended ? "Reactivate" : "Suspend"} {botName}?
        </span>
        <Button
          size="sm"
          variant={isSuspended ? "default" : "danger"}
          onClick={handleSuspend}
          disabled={loading}
        >
          {loading ? "..." : "Confirm"}
        </Button>
        <Button size="sm" variant="ghost" onClick={handleCancel}>
          Cancel
        </Button>
      </div>
    );
  }

  return (
    <Button
      size="sm"
      variant={isSuspended ? "outline" : "danger"}
      onClick={handleSuspend}
      className={cn(
        "gap-1.5",
        isSuspended && "text-success border-success hover:bg-success/10"
      )}
    >
      {isSuspended ? (
        <>
          <Shield className="h-3.5 w-3.5" />
          Reactivate
        </>
      ) : (
        <>
          <AlertTriangle className="h-3.5 w-3.5" />
          Suspend
        </>
      )}
    </Button>
  );
}
