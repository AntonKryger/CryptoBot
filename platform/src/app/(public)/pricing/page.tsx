"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { Check, Activity } from "lucide-react";
import { TIERS } from "@/lib/constants";
import { formatCurrency } from "@/lib/utils";
import { createBrowserClient } from "@supabase/ssr";

type TierKey = keyof typeof TIERS;

export default function PricingPage() {
  const [isLoggedIn, setIsLoggedIn] = useState(false);

  useEffect(() => {
    // Check if Supabase is configured before attempting auth check
    const url = process.env.NEXT_PUBLIC_SUPABASE_URL;
    const key = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;
    if (!url || !key) return;

    const supabase = createBrowserClient(url, key);
    supabase.auth.getUser().then(({ data }) => {
      if (data.user) setIsLoggedIn(true);
    });
  }, []);

  function getHref(tier: TierKey) {
    if (isLoggedIn) return `/checkout?tier=${tier}`;
    return `/signup?tier=${tier}`;
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
          <div className="flex items-center gap-4 md:gap-6">
            {!isLoggedIn && (
              <>
                <Link
                  href="/login"
                  className="text-xs uppercase tracking-wider text-white/40 hover:text-white transition-colors"
                >
                  Log in
                </Link>
                <Link
                  href="/signup"
                  className="text-xs uppercase tracking-wider bg-gradient-to-r from-violet-500 to-fuchsia-500 text-white px-5 py-2 rounded-full font-semibold hover:opacity-90 transition-all"
                >
                  Get Started
                </Link>
              </>
            )}
          </div>
        </div>
      </nav>

      {/* Header */}
      <section className="pt-32 pb-8 text-center px-8">
        <div className="text-xs uppercase tracking-widest text-white/30 mb-4">
          Pricing
        </div>
        <h1 className="text-5xl md:text-6xl font-bold tracking-tight mb-4">
          Simple, transparent pricing
        </h1>
        <p className="text-lg text-white/40 max-w-xl mx-auto">
          One-time setup fee to get started, then a low monthly subscription.
          Cancel anytime.
        </p>
      </section>

      {/* Pricing Cards */}
      <section className="max-w-5xl mx-auto px-8 py-16">
        <div className="grid md:grid-cols-3 gap-6">
          {(Object.entries(TIERS) as [TierKey, (typeof TIERS)[TierKey]][]).map(
            ([key, tier]) => (
              <div
                key={key}
                className={`rounded-3xl p-10 h-full flex flex-col relative overflow-hidden ${
                  key === "pro"
                    ? "bg-gradient-to-b from-violet-500/10 to-fuchsia-500/5 border border-violet-500/20 shadow-[0_0_40px_rgba(139,92,246,0.1)]"
                    : "glass-card"
                }`}
              >
                {key === "pro" && (
                  <div className="absolute -top-3 left-1/2 -translate-x-1/2 px-4 py-1 bg-gradient-to-r from-violet-500 to-fuchsia-500 rounded-full text-xs font-semibold">
                    Recommended
                  </div>
                )}
                <div
                  className={`text-xs uppercase tracking-widest mb-8 ${
                    key === "pro" ? "text-violet-300/50" : "text-white/30"
                  }`}
                >
                  {tier.name}
                </div>
                <div className="mb-2">
                  <span className="text-5xl font-bold tracking-tight">
                    {formatCurrency(tier.oneTime)}
                  </span>
                </div>
                <div
                  className={`text-sm mb-10 ${
                    key === "pro" ? "text-white/40" : "text-white/30"
                  }`}
                >
                  then {formatCurrency(tier.monthly)}/mo
                </div>
                <ul className="space-y-3 mb-10 flex-1">
                  {tier.features.map((f) => (
                    <li
                      key={f}
                      className={`flex items-center gap-3 text-sm ${
                        key === "pro" ? "text-white/50" : "text-white/40"
                      }`}
                    >
                      <Check
                        className={`w-3.5 h-3.5 flex-shrink-0 ${
                          key === "pro" ? "text-violet-400" : "text-white/20"
                        }`}
                      />
                      {f}
                    </li>
                  ))}
                </ul>
                <Link
                  href={getHref(key)}
                  className={`w-full py-3.5 rounded-full font-semibold text-sm transition-all text-center block ${
                    key === "pro"
                      ? "bg-gradient-to-r from-violet-500 to-fuchsia-500 text-white hover:opacity-90"
                      : "bg-white/5 hover:bg-white/10 border border-white/10"
                  }`}
                >
                  Get Started
                </Link>
              </div>
            )
          )}
        </div>
      </section>

      {/* Footer */}
      <footer className="border-t border-white/5 py-8">
        <div className="max-w-5xl mx-auto px-8 flex items-center justify-between text-xs text-white/15">
          <span>&copy; 2026 CryptoBot</span>
          <div className="flex gap-6">
            <span className="hover:text-white/30 cursor-default">Privacy</span>
            <span className="hover:text-white/30 cursor-default">Terms</span>
            <span className="hover:text-white/30 cursor-default">Support</span>
          </div>
        </div>
      </footer>
    </div>
  );
}
