"use client";

import { useState, useEffect, useCallback, useRef } from "react";
import {
  MessageCircle,
  Send,
  RefreshCw,
  CheckCircle,
  XCircle,
} from "lucide-react";

type State =
  | { step: "idle" }
  | { step: "generating" }
  | { step: "pending"; code: string; expiresAt: number }
  | { step: "connected"; chatId: string }
  | { step: "error"; message: string };

export function TelegramSetup() {
  const [state, setState] = useState<State>({ step: "idle" });
  const [secondsLeft, setSecondsLeft] = useState(0);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // Check initial status on mount
  useEffect(() => {
    checkStatus();
    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
      if (timerRef.current) clearInterval(timerRef.current);
    };
  }, []);

  const checkStatus = useCallback(async () => {
    try {
      const res = await fetch("/api/telegram/status");
      if (!res.ok) return;
      const data = await res.json();
      if (data.connected) {
        setState({ step: "connected", chatId: data.chatId });
        stopPolling();
      }
    } catch {
      // Silently fail on initial check
    }
  }, []);

  function stopPolling() {
    if (pollRef.current) {
      clearInterval(pollRef.current);
      pollRef.current = null;
    }
    if (timerRef.current) {
      clearInterval(timerRef.current);
      timerRef.current = null;
    }
  }

  async function generateCode() {
    setState({ step: "generating" });
    stopPolling();

    try {
      const res = await fetch("/api/telegram/generate-code", {
        method: "POST",
      });

      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        throw new Error(data.error || "Failed to generate code");
      }

      const { code, expiresAt } = await res.json();
      const expiresAtMs = new Date(expiresAt).getTime();

      setState({ step: "pending", code, expiresAt: expiresAtMs });
      setSecondsLeft(Math.max(0, Math.floor((expiresAtMs - Date.now()) / 1000)));

      // Countdown timer
      timerRef.current = setInterval(() => {
        setSecondsLeft((prev) => {
          if (prev <= 1) {
            stopPolling();
            setState({ step: "idle" });
            return 0;
          }
          return prev - 1;
        });
      }, 1000);

      // Poll for verification every 5 seconds
      pollRef.current = setInterval(async () => {
        try {
          const statusRes = await fetch("/api/telegram/status");
          if (!statusRes.ok) return;
          const statusData = await statusRes.json();

          if (statusData.connected) {
            setState({ step: "connected", chatId: statusData.chatId });
            stopPolling();
          } else if (statusData.codeExpired) {
            setState({ step: "idle" });
            stopPolling();
          }
        } catch {
          // Retry on next interval
        }
      }, 5000);
    } catch (err) {
      setState({
        step: "error",
        message: err instanceof Error ? err.message : "Unknown error",
      });
    }
  }

  async function disconnect() {
    try {
      const res = await fetch("/api/telegram/disconnect", { method: "POST" });
      if (res.ok) {
        setState({ step: "idle" });
      }
    } catch {
      setState({ step: "error", message: "Failed to disconnect" });
    }
  }

  function maskChatId(chatId: string): string {
    if (chatId.length <= 4) return "****";
    return "****" + chatId.slice(-4);
  }

  function formatTime(seconds: number): string {
    const m = Math.floor(seconds / 60);
    const s = seconds % 60;
    return `${m}:${s.toString().padStart(2, "0")}`;
  }

  // Connected state
  if (state.step === "connected") {
    return (
      <div className="rounded-xl border border-border bg-bg-secondary p-6">
        <div className="flex items-center gap-3 mb-6">
          <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-success/20">
            <CheckCircle className="h-5 w-5 text-success" />
          </div>
          <div>
            <h3 className="text-sm font-semibold text-text-primary">
              Telegram Connected
            </h3>
            <p className="text-xs text-text-muted">
              Notifications are active
            </p>
          </div>
          <span className="ml-auto inline-flex items-center rounded-full bg-success/20 px-2.5 py-0.5 text-xs font-medium text-success">
            Connected
          </span>
        </div>

        <div className="rounded-lg border border-border bg-bg-primary p-4 mb-6">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-xs text-text-muted">Chat ID</p>
              <p className="text-sm font-mono text-text-primary mt-0.5">
                {maskChatId(state.chatId)}
              </p>
            </div>
            <MessageCircle className="h-5 w-5 text-text-muted" />
          </div>
        </div>

        <button
          onClick={disconnect}
          className="flex items-center gap-2 rounded-lg border border-danger/30 bg-danger/10 px-4 py-2 text-sm font-medium text-danger transition-colors hover:bg-danger/20"
        >
          <XCircle className="h-4 w-4" />
          Disconnect Telegram
        </button>
      </div>
    );
  }

  // Pending verification state
  if (state.step === "pending") {
    return (
      <div className="rounded-xl border border-border bg-bg-secondary p-6">
        <div className="flex items-center gap-3 mb-6">
          <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-accent/20">
            <Send className="h-5 w-5 text-accent" />
          </div>
          <div>
            <h3 className="text-sm font-semibold text-text-primary">
              Step 2: Send Verification Code
            </h3>
            <p className="text-xs text-text-muted">
              Send this code to our Telegram bot
            </p>
          </div>
        </div>

        {/* Code display */}
        <div className="rounded-lg border border-accent/30 bg-accent/5 p-6 text-center mb-4">
          <p className="text-xs text-text-muted mb-2">Your verification code</p>
          <p className="text-4xl font-mono font-bold tracking-[0.3em] text-accent">
            {state.code}
          </p>
          <p className="text-xs text-text-muted mt-3">
            Expires in{" "}
            <span className="font-mono text-text-primary">
              {formatTime(secondsLeft)}
            </span>
          </p>
        </div>

        {/* Instructions */}
        <div className="rounded-lg border border-border bg-bg-primary p-4 mb-4">
          <ol className="space-y-2 text-sm text-text-secondary">
            <li className="flex items-start gap-2">
              <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-accent/20 text-xs font-bold text-accent">
                1
              </span>
              Open Telegram and search for{" "}
              <span className="font-mono text-accent">@CryptoBotAlerts</span>
            </li>
            <li className="flex items-start gap-2">
              <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-accent/20 text-xs font-bold text-accent">
                2
              </span>
              Send the 6-digit code shown above
            </li>
            <li className="flex items-start gap-2">
              <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-accent/20 text-xs font-bold text-accent">
                3
              </span>
              This page will update automatically when verified
            </li>
          </ol>
        </div>

        {/* Polling indicator */}
        <div className="flex items-center gap-2 text-xs text-text-muted">
          <RefreshCw className="h-3 w-3 animate-spin" />
          Waiting for verification...
        </div>
      </div>
    );
  }

  // Generating state
  if (state.step === "generating") {
    return (
      <div className="rounded-xl border border-border bg-bg-secondary p-6">
        <div className="flex items-center justify-center py-12">
          <RefreshCw className="h-6 w-6 animate-spin text-accent" />
          <span className="ml-3 text-sm text-text-muted">
            Generating verification code...
          </span>
        </div>
      </div>
    );
  }

  // Error state
  if (state.step === "error") {
    return (
      <div className="rounded-xl border border-border bg-bg-secondary p-6">
        <div className="flex items-center gap-3 mb-4">
          <XCircle className="h-5 w-5 text-danger" />
          <p className="text-sm text-danger">{state.message}</p>
        </div>
        <button
          onClick={() => setState({ step: "idle" })}
          className="text-sm text-accent hover:underline"
        >
          Try again
        </button>
      </div>
    );
  }

  // Idle / initial state
  return (
    <div className="rounded-xl border border-border bg-bg-secondary p-6">
      <div className="flex items-center gap-3 mb-6">
        <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-accent/20">
          <MessageCircle className="h-5 w-5 text-accent" />
        </div>
        <div>
          <h3 className="text-sm font-semibold text-text-primary">
            Step 1: Connect Telegram
          </h3>
          <p className="text-xs text-text-muted">
            Link your Telegram account for real-time alerts
          </p>
        </div>
      </div>

      {/* What you'll receive */}
      <div className="rounded-lg border border-border bg-bg-primary p-4 mb-6">
        <p className="text-xs font-semibold text-text-primary mb-3 uppercase tracking-wider">
          Notifications you will receive
        </p>
        <ul className="space-y-2 text-sm text-text-secondary">
          <li className="flex items-center gap-2">
            <CheckCircle className="h-3.5 w-3.5 text-success" />
            Trade opened / closed alerts
          </li>
          <li className="flex items-center gap-2">
            <CheckCircle className="h-3.5 w-3.5 text-success" />
            Daily P/L summary
          </li>
          <li className="flex items-center gap-2">
            <CheckCircle className="h-3.5 w-3.5 text-success" />
            Bot status changes (started, stopped, errors)
          </li>
          <li className="flex items-center gap-2">
            <CheckCircle className="h-3.5 w-3.5 text-success" />
            Risk alerts (circuit breaker, max drawdown)
          </li>
        </ul>
      </div>

      <button
        onClick={generateCode}
        className="flex items-center gap-2 rounded-lg bg-accent px-5 py-2.5 text-sm font-medium text-white transition-colors hover:bg-accent/90"
      >
        <MessageCircle className="h-4 w-4" />
        Generate Verification Code
      </button>
    </div>
  );
}
