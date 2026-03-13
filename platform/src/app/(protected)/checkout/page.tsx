"use client";

import { useState } from "react";
import { useSearchParams } from "next/navigation";
import Link from "next/link";
import { Suspense } from "react";
import {
  Activity,
  CreditCard,
  Shield,
  Loader2,
  Check,
  AlertCircle,
} from "lucide-react";
import { TIERS } from "@/lib/constants";
import { formatCurrency } from "@/lib/utils";
import type { Tier } from "@/lib/supabase/types";

function CheckoutContent() {
  const searchParams = useSearchParams();
  const tierParam = searchParams.get("tier") as Tier | null;
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const validTier =
    tierParam && tierParam in TIERS ? tierParam : null;
  const tier = validTier ? TIERS[validTier] : null;

  if (!validTier || !tier) {
    return (
      <div className="min-h-screen bg-[#06080f] text-white flex items-center justify-center px-8">
        <div className="text-center">
          <AlertCircle className="w-12 h-12 text-red-400 mx-auto mb-4" />
          <h1 className="text-2xl font-bold mb-2">Invalid plan selected</h1>
          <p className="text-white/40 mb-6">
            Please choose a plan from the pricing page.
          </p>
          <Link
            href="/pricing"
            className="inline-flex items-center gap-2 bg-gradient-to-r from-violet-500 to-fuchsia-500 text-white font-semibold px-6 py-3 rounded-full hover:opacity-90 transition-all"
          >
            View Plans
          </Link>
        </div>
      </div>
    );
  }

  async function handleCheckout() {
    setLoading(true);
    setError(null);

    try {
      const res = await fetch("/api/stripe/checkout-session", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ tier: validTier }),
      });

      const data = await res.json();

      if (!res.ok) {
        setError(data.error || "Something went wrong. Please try again.");
        setLoading(false);
        return;
      }

      // Redirect to Stripe Checkout
      if (data.url) {
        window.location.href = data.url;
      } else {
        setError("No checkout URL returned. Please try again.");
        setLoading(false);
      }
    } catch {
      setError("Network error. Please check your connection and try again.");
      setLoading(false);
    }
  }

  return (
    <div className="min-h-screen bg-[#06080f] text-white">
      {/* Nav */}
      <nav className="fixed top-0 w-full z-50 bg-[#06080f]/80 backdrop-blur-xl border-b border-white/5">
        <div className="max-w-6xl mx-auto px-8 h-16 flex items-center justify-between">
          <Link href="/" className="flex items-center gap-2.5">
            <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-violet-500 to-fuchsia-500 flex items-center justify-center">
              <Activity className="w-4 h-4 text-white" />
            </div>
            <span className="font-bold text-lg tracking-tight">CryptoBot</span>
          </Link>
          <Link
            href="/pricing"
            className="text-xs uppercase tracking-wider text-white/40 hover:text-white transition-colors"
          >
            Back to Pricing
          </Link>
        </div>
      </nav>

      {/* Checkout Content */}
      <div className="pt-32 pb-20 px-8 max-w-lg mx-auto">
        <h1 className="text-3xl font-bold tracking-tight mb-2">Checkout</h1>
        <p className="text-white/40 mb-10">
          Complete your purchase to start trading.
        </p>

        {/* Order Summary */}
        <div className="rounded-2xl border border-white/10 bg-white/[0.03] p-8 mb-8">
          <h2 className="text-sm uppercase tracking-widest text-white/30 mb-6">
            Order Summary
          </h2>

          <div className="flex items-center justify-between mb-6">
            <div>
              <div className="text-xl font-bold">{tier.name} Plan</div>
              <div className="text-sm text-white/40 mt-1">
                One-time setup + monthly subscription
              </div>
            </div>
            {validTier === "pro" && (
              <span className="px-3 py-1 bg-gradient-to-r from-violet-500 to-fuchsia-500 rounded-full text-xs font-semibold">
                Popular
              </span>
            )}
          </div>

          <div className="border-t border-white/5 pt-4 space-y-3">
            <div className="flex justify-between text-sm">
              <span className="text-white/50">Setup fee (one-time)</span>
              <span className="font-mono">
                {formatCurrency(tier.oneTime)}
              </span>
            </div>
            <div className="flex justify-between text-sm">
              <span className="text-white/50">Monthly subscription</span>
              <span className="font-mono">
                {formatCurrency(tier.monthly)}/mo
              </span>
            </div>
            <div className="border-t border-white/5 pt-3 flex justify-between">
              <span className="text-white/70 font-medium">Due today</span>
              <span className="font-mono font-bold text-lg">
                {formatCurrency(tier.oneTime + tier.monthly)}
              </span>
            </div>
          </div>
        </div>

        {/* Features included */}
        <div className="rounded-2xl border border-white/10 bg-white/[0.03] p-8 mb-8">
          <h2 className="text-sm uppercase tracking-widest text-white/30 mb-4">
            What&apos;s included
          </h2>
          <ul className="space-y-2.5">
            {tier.features.map((f) => (
              <li
                key={f}
                className="flex items-center gap-3 text-sm text-white/50"
              >
                <Check className="w-3.5 h-3.5 text-violet-400 flex-shrink-0" />
                {f}
              </li>
            ))}
          </ul>
        </div>

        {/* Error */}
        {error && (
          <div className="rounded-xl bg-red-500/10 border border-red-500/20 p-4 mb-6 flex items-start gap-3">
            <AlertCircle className="w-5 h-5 text-red-400 flex-shrink-0 mt-0.5" />
            <p className="text-sm text-red-300">{error}</p>
          </div>
        )}

        {/* Pay Button */}
        <button
          onClick={handleCheckout}
          disabled={loading}
          className="w-full py-4 rounded-full font-semibold text-base bg-gradient-to-r from-violet-500 to-fuchsia-500 text-white hover:opacity-90 transition-all disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-3"
        >
          {loading ? (
            <>
              <Loader2 className="w-5 h-5 animate-spin" />
              Redirecting to Stripe...
            </>
          ) : (
            <>
              <CreditCard className="w-5 h-5" />
              Pay with Stripe
            </>
          )}
        </button>

        {/* Trust badges */}
        <div className="mt-6 flex items-center justify-center gap-6 text-xs text-white/20">
          <div className="flex items-center gap-1.5">
            <Shield className="w-3.5 h-3.5" />
            <span>SSL Encrypted</span>
          </div>
          <div className="flex items-center gap-1.5">
            <CreditCard className="w-3.5 h-3.5" />
            <span>Powered by Stripe</span>
          </div>
        </div>
      </div>
    </div>
  );
}

export default function CheckoutPage() {
  return (
    <Suspense
      fallback={
        <div className="min-h-screen bg-[#06080f] text-white flex items-center justify-center">
          <Loader2 className="w-8 h-8 animate-spin text-violet-400" />
        </div>
      }
    >
      <CheckoutContent />
    </Suspense>
  );
}
