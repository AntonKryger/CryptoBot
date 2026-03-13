"use client";

import { useState, useEffect, useRef } from "react";
import Link from "next/link";
import { TIERS } from "@/lib/constants";
import { formatCurrency } from "@/lib/utils";
import { RevealSection } from "@/hooks/useInView";
import {
  ArrowRight,
  Check,
  Minus,
  Wallet,
  TrendingUp,
  BarChart3,
  Activity,
  Globe,
} from "lucide-react";
import {
  translations,
  LANGUAGES,
  LANGUAGE_LABELS,
  type Language,
} from "@/lib/translations";

const MOCK_TRADES = [
  { pair: "BTC/USD", dir: "BUY", pnl: "+382.50", positive: true },
  { pair: "ETH/USD", dir: "BUY", pnl: "+124.80", positive: true },
  { pair: "SOL/USD", dir: "SELL", pnl: "+67.20", positive: true },
  { pair: "LTC/USD", dir: "BUY", pnl: "-23.10", positive: false },
];

function LanguageSelector({
  lang,
  setLang,
}: {
  lang: Language;
  setLang: (l: Language) => void;
}) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    function handleClick(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) {
        setOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, []);

  return (
    <div className="relative" ref={ref}>
      <button
        onClick={() => setOpen(!open)}
        className="flex items-center gap-1.5 text-xs text-white/40 hover:text-white transition-colors uppercase tracking-wider"
      >
        <Globe className="w-3.5 h-3.5" />
        {lang.toUpperCase()}
      </button>
      {open && (
        <div className="absolute top-full right-0 mt-2 py-1 bg-[#12151f] border border-white/10 rounded-lg shadow-xl min-w-[140px] z-50">
          {LANGUAGES.map((l) => (
            <button
              key={l}
              onClick={() => {
                setLang(l);
                setOpen(false);
              }}
              className={`w-full text-left px-4 py-2 text-sm transition-colors ${
                l === lang
                  ? "text-violet-400 bg-violet-500/10"
                  : "text-white/60 hover:text-white hover:bg-white/5"
              }`}
            >
              {LANGUAGE_LABELS[l]}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

export default function LandingPage() {
  const [lang, setLang] = useState<Language>("en");
  const [isLoggedIn, setIsLoggedIn] = useState(false);
  const t = translations[lang];

  // Persist language choice
  useEffect(() => {
    const saved = localStorage.getItem("lang") as Language | null;
    if (saved && LANGUAGES.includes(saved)) setLang(saved);
  }, []);
  useEffect(() => {
    localStorage.setItem("lang", lang);
  }, [lang]);

  // Check auth state
  useEffect(() => {
    const url = process.env.NEXT_PUBLIC_SUPABASE_URL;
    const key = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;
    if (!url || !key) return;
    import("@supabase/ssr").then(({ createBrowserClient }) => {
      const supabase = createBrowserClient(url, key);
      supabase.auth.getUser().then(({ data }) => {
        if (data.user) setIsLoggedIn(true);
      });
    });
  }, []);

  return (
    <div className="min-h-screen bg-[#06080f] text-white overflow-hidden">
      {/* Nav */}
      <nav className="fixed top-0 w-full z-50 bg-[#06080f]/80 backdrop-blur-xl border-b border-white/5">
        <div className="max-w-6xl mx-auto px-8 h-16 flex items-center justify-between">
          <div className="flex items-center gap-2.5">
            <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-violet-500 to-fuchsia-500 flex items-center justify-center">
              <Activity className="w-4 h-4 text-white" />
            </div>
            <span className="font-bold text-lg tracking-tight">CryptoBot</span>
          </div>
          <div className="flex items-center gap-4 md:gap-6">
            <LanguageSelector lang={lang} setLang={setLang} />
            <a
              href="#pricing"
              className="text-xs text-white/40 hover:text-white transition-colors uppercase tracking-wider"
            >
              {t.nav.pricing}
            </a>
            {isLoggedIn ? (
              <Link
                href="/pricing"
                className="text-xs uppercase tracking-wider bg-gradient-to-r from-violet-500 to-fuchsia-500 text-white px-5 py-2 rounded-full font-semibold hover:opacity-90 transition-all"
              >
                {t.nav.pricing}
              </Link>
            ) : (
              <>
                <Link
                  href="/login"
                  className="text-xs uppercase tracking-wider text-white/40 hover:text-white transition-colors"
                >
                  {t.nav.login}
                </Link>
                <Link
                  href="/signup"
                  className="text-xs uppercase tracking-wider bg-gradient-to-r from-violet-500 to-fuchsia-500 text-white px-5 py-2 rounded-full font-semibold hover:opacity-90 transition-all"
                >
                  {t.nav.getStarted}
                </Link>
              </>
            )}
          </div>
        </div>
      </nav>

      {/* === HERO === */}
      <section className="min-h-screen flex flex-col items-center justify-center px-8 relative">
        <div className="absolute top-1/3 left-1/3 w-[500px] h-[500px] bg-violet-600/[0.08] blur-[150px] rounded-full" />
        <div className="absolute bottom-1/3 right-1/3 w-[400px] h-[400px] bg-fuchsia-500/[0.06] blur-[120px] rounded-full" />

        <div className="relative text-center">
          <h1 className="text-4xl sm:text-6xl lg:text-7xl xl:text-[9rem] font-bold tracking-tighter leading-[0.85]">
            {t.hero.line1}
            <br />
            {t.hero.line2}
            <br />
            <span className="bg-gradient-to-r from-violet-400 via-fuchsia-400 to-violet-400 bg-clip-text text-transparent">
              {t.hero.line3}
            </span>
          </h1>
          <div className="mt-12 flex items-center justify-center gap-6">
            <Link
              href={isLoggedIn ? "/pricing" : "/signup"}
              className="group flex items-center gap-3 bg-gradient-to-r from-violet-500 to-fuchsia-500 text-white font-semibold px-8 py-3.5 rounded-full hover:shadow-[0_0_30px_rgba(139,92,246,0.3)] transition-all"
            >
              {t.hero.getStarted}
              <ArrowRight className="w-4 h-4 group-hover:translate-x-1 transition-transform" />
            </Link>
            <a
              href="#dashboard"
              className="group flex items-center gap-3 text-white/50 hover:text-white transition-colors text-lg"
            >
              <span>{t.hero.discoverHow}</span>
              <ArrowRight className="w-5 h-5 group-hover:translate-x-2 transition-transform" />
            </a>
          </div>
        </div>
      </section>

      {/* === STATEMENT === */}
      <RevealSection>
        <section className="max-w-4xl mx-auto px-8 py-32">
          <p className="text-3xl md:text-5xl font-light leading-snug text-white/60">
            {t.statement.part1}{" "}
            <span className="text-white font-medium">
              {t.statement.highlight1}
            </span>{" "}
            {t.statement.part2}{" "}
            <span className="text-violet-400 font-medium">
              {t.statement.highlight2}
            </span>
          </p>
        </section>
      </RevealSection>

      {/* === DASHBOARD SHOWCASE === */}
      <RevealSection>
        <section
          id="dashboard"
          className="max-w-6xl mx-auto px-6 pb-16 relative"
        >
          <div className="absolute inset-0 bg-gradient-to-b from-violet-500/20 via-fuchsia-500/10 to-transparent blur-[80px] -top-20" />

          <div className="relative rounded-2xl border border-white/10 bg-[#0a0d18]/90 backdrop-blur-sm overflow-hidden shadow-[0_0_80px_rgba(139,92,246,0.15)]">
            <div className="flex items-center gap-2 px-5 py-3 border-b border-white/5">
              <div className="w-3 h-3 rounded-full bg-red-500/60" />
              <div className="w-3 h-3 rounded-full bg-yellow-500/60" />
              <div className="w-3 h-3 rounded-full bg-green-500/60" />
              <span className="ml-3 text-xs text-white/20 font-mono">
                dashboard.cryptobot.io
              </span>
            </div>

            <div className="p-6">
              <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
                {[
                  { label: t.dashboard.balance, value: "€12,450", change: "+24.5%", icon: Wallet },
                  { label: t.dashboard.todayPl, value: "+€234.50", change: "+1.92%", icon: TrendingUp },
                  { label: t.dashboard.openPositions, value: "2", change: t.dashboard.ofMax, icon: BarChart3 },
                  { label: t.dashboard.winRate, value: "67.3%", change: "+3.2%", icon: Activity },
                ].map((stat) => (
                  <div
                    key={stat.label}
                    className="bg-white/[0.03] rounded-xl p-4 border border-white/5"
                  >
                    <div className="flex items-center justify-between mb-3">
                      <span className="text-xs text-white/30">{stat.label}</span>
                      <stat.icon className="w-4 h-4 text-white/20" />
                    </div>
                    <div className="text-xl font-bold font-mono">{stat.value}</div>
                    <div className="text-xs text-emerald-400 mt-1">{stat.change}</div>
                  </div>
                ))}
              </div>

              <div className="grid md:grid-cols-5 gap-4">
                <div className="md:col-span-3 bg-white/[0.02] rounded-xl p-5 border border-white/5">
                  <div className="text-sm font-medium mb-4">
                    {t.dashboard.balanceHistory}
                  </div>
                  <div className="h-40 flex items-end gap-1">
                    {[40,42,38,45,50,48,52,55,53,58,62,60,65,70,68,72,75,78,80,85,82,88,90,92].map((h, i) => (
                      <div
                        key={i}
                        className="flex-1 rounded-t bg-gradient-to-t from-violet-500/40 to-violet-500/10"
                        style={{ height: `${h}%` }}
                      />
                    ))}
                  </div>
                </div>
                <div className="md:col-span-2 bg-white/[0.02] rounded-xl p-5 border border-white/5">
                  <div className="text-sm font-medium mb-4">
                    {t.dashboard.recentTrades}
                  </div>
                  <div className="space-y-3">
                    {MOCK_TRADES.map((tr, i) => (
                      <div key={i} className="flex items-center justify-between text-xs">
                        <div className="flex items-center gap-3">
                          <span className="font-mono text-white/70">{tr.pair}</span>
                          <span
                            className={`px-1.5 py-0.5 rounded text-[10px] font-medium ${
                              tr.dir === "BUY"
                                ? "bg-emerald-500/10 text-emerald-400"
                                : "bg-red-500/10 text-red-400"
                            }`}
                          >
                            {tr.dir}
                          </span>
                        </div>
                        <span
                          className={`font-mono ${tr.positive ? "text-emerald-400" : "text-red-400"}`}
                        >
                          €{tr.pnl}
                        </span>
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            </div>
          </div>
        </section>
      </RevealSection>

      {/* === STATS BAR === */}
      <RevealSection>
        <section className="max-w-5xl mx-auto px-6 py-20">
          <div className="grid grid-cols-2 md:grid-cols-4 gap-8 text-center">
            {[
              { value: "€2.4M+", label: t.stats.totalVolume },
              { value: "12,847", label: t.stats.tradesExecuted },
              { value: "99.7%", label: t.stats.uptime },
              { value: "<200ms", label: t.stats.avgExecution },
            ].map((s) => (
              <div key={s.label}>
                <div className="text-3xl font-bold font-mono bg-gradient-to-b from-white to-white/60 bg-clip-text text-transparent">
                  {s.value}
                </div>
                <div className="text-xs text-white/30 mt-1">{s.label}</div>
              </div>
            ))}
          </div>
        </section>
      </RevealSection>

      {/* === COMPARISON === */}
      <section className="border-y border-white/5 bg-white/[0.01]">
        <div className="max-w-4xl mx-auto px-8 py-28">
          <RevealSection className="text-center mb-16">
            <h2 className="text-4xl md:text-5xl font-bold mb-4">
              {t.comparison.title1}{" "}
              <span className="line-through text-white/20">
                {t.comparison.strikethrough}
              </span>{" "}
              <span className="bg-gradient-to-r from-violet-400 to-fuchsia-400 bg-clip-text text-transparent">
                {t.comparison.title2}
              </span>
            </h2>
          </RevealSection>

          <RevealSection delay={200}>
            <div className="grid md:grid-cols-2 gap-6">
              <div className="rounded-2xl p-8 bg-red-500/[0.03] border border-red-500/10">
                <div className="text-sm font-medium text-red-400 mb-6">
                  {t.comparison.manualTitle}
                </div>
                <ul className="space-y-4">
                  {t.comparison.manual.map((item) => (
                    <li key={item} className="flex items-start gap-3 text-sm text-white/40">
                      <span className="text-red-400/60 mt-0.5">✕</span>
                      {item}
                    </li>
                  ))}
                </ul>
              </div>
              <div className="rounded-2xl p-8 bg-violet-500/[0.03] border border-violet-500/10">
                <div className="text-sm font-medium text-violet-400 mb-6">
                  {t.comparison.botTitle}
                </div>
                <ul className="space-y-4">
                  {t.comparison.bot.map((item) => (
                    <li key={item} className="flex items-start gap-3 text-sm text-white/60">
                      <Check className="w-4 h-4 text-violet-400 flex-shrink-0 mt-0.5" />
                      {item}
                    </li>
                  ))}
                </ul>
              </div>
            </div>
          </RevealSection>
        </div>
      </section>

      {/* === FEATURE SECTIONS === */}
      <section>
        {/* Signal Engine */}
        <div className="max-w-6xl mx-auto px-8 py-32 grid md:grid-cols-2 gap-20 items-center">
          <RevealSection>
            <div>
              <div className="text-xs uppercase tracking-widest text-violet-400/60 mb-6">
                {t.features.signal.label}
              </div>
              <h2 className="text-4xl md:text-5xl font-bold tracking-tight mb-6 leading-tight">
                {t.features.signal.title1}
                <br />
                {t.features.signal.title2}
              </h2>
              <p className="text-lg text-white/40 leading-relaxed">
                {t.features.signal.desc}
              </p>
            </div>
          </RevealSection>
          <RevealSection delay={200}>
            <div className="relative">
              <div className="absolute inset-0 bg-gradient-to-br from-violet-500/[0.08] to-fuchsia-500/[0.04] rounded-3xl blur-xl" />
              <div className="relative glass-card rounded-3xl p-8">
                <div className="font-mono text-xs text-white/30 mb-6">
                  {t.features.signal.liveOutput}
                </div>
                <div className="space-y-4 font-mono text-sm">
                  <div className="flex justify-between text-white/50">
                    <span>BTCUSD</span>
                    <span className="text-emerald-400">
                      {t.features.signal.confidence}
                    </span>
                  </div>
                  <div className="w-full h-px bg-white/5" />
                  <div className="grid grid-cols-2 gap-4 text-xs text-white/30">
                    <div>RSI <span className="text-white/60 ml-2">42.3</span></div>
                    <div>ADX <span className="text-white/60 ml-2">28.7</span></div>
                    <div>Sentiment <span className="text-emerald-400 ml-2">+0.72</span></div>
                    <div>R:R <span className="text-white/60 ml-2">2.4:1</span></div>
                  </div>
                  <div className="w-full h-px bg-white/5" />
                  <div className="text-white/30">
                    Entry <span className="text-white ml-2">$67,300</span>
                    <span className="mx-4">→</span>
                    TP <span className="text-emerald-400 ml-2">$69,200</span>
                  </div>
                </div>
              </div>
            </div>
          </RevealSection>
        </div>

        <div className="border-t border-white/5" />

        {/* Risk Management */}
        <div className="max-w-6xl mx-auto px-8 py-32 grid md:grid-cols-2 gap-20 items-center">
          <RevealSection delay={200} className="md:order-2">
            <div>
              <div className="text-xs uppercase tracking-widest text-fuchsia-400/60 mb-6">
                {t.features.risk.label}
              </div>
              <h2 className="text-4xl md:text-5xl font-bold tracking-tight mb-6 leading-tight">
                {t.features.risk.title1}
                <br />
                {t.features.risk.title2}
              </h2>
              <p className="text-lg text-white/40 leading-relaxed mb-8">
                {t.features.risk.desc}
              </p>
              <div className="space-y-3">
                {t.features.risk.gates.map((gate, i) => (
                  <div key={gate} className="flex items-center gap-3 text-sm">
                    <div className="w-6 h-6 rounded-full bg-violet-500/10 border border-violet-500/20 flex items-center justify-center text-[10px] text-violet-400 font-mono">
                      {i + 1}
                    </div>
                    <span className="text-white/50">{gate}</span>
                  </div>
                ))}
              </div>
            </div>
          </RevealSection>
          <RevealSection className="md:order-1">
            <div className="relative">
              <div className="absolute inset-0 bg-gradient-to-br from-violet-500/[0.06] to-fuchsia-500/[0.03] rounded-3xl blur-xl" />
              <div className="relative glass-card rounded-3xl p-8 text-center">
                <div className="text-8xl font-bold bg-gradient-to-b from-violet-400/20 to-violet-400/5 bg-clip-text text-transparent mb-4">
                  7
                </div>
                <div className="text-lg text-white/40">
                  {t.features.risk.gatesLabel}
                </div>
                <div className="text-sm text-white/20 mt-2">
                  {t.features.risk.gatesSub}
                </div>
                <div className="mt-8 flex items-center justify-center gap-2">
                  {Array.from({ length: 7 }).map((_, i) => (
                    <div
                      key={i}
                      className="w-8 h-8 rounded-lg bg-violet-500/10 border border-violet-500/20 flex items-center justify-center"
                    >
                      <Check className="w-3.5 h-3.5 text-violet-400" />
                    </div>
                  ))}
                </div>
              </div>
            </div>
          </RevealSection>
        </div>

        <div className="border-t border-white/5" />

        {/* Transparency */}
        <div className="max-w-6xl mx-auto px-8 py-32 grid md:grid-cols-2 gap-20 items-center">
          <RevealSection>
            <div>
              <div className="text-xs uppercase tracking-widest text-fuchsia-400/60 mb-6">
                {t.features.transparency.label}
              </div>
              <h2 className="text-4xl md:text-5xl font-bold tracking-tight mb-6 leading-tight">
                {t.features.transparency.title1}
                <br />
                {t.features.transparency.title2}
              </h2>
              <p className="text-lg text-white/40 leading-relaxed">
                {t.features.transparency.desc}
              </p>
            </div>
          </RevealSection>
          <RevealSection delay={200}>
            <div className="glass-card rounded-3xl p-1 overflow-hidden">
              <div className="bg-white/[0.02] rounded-2xl p-6 space-y-4">
                <div className="grid grid-cols-2 gap-3">
                  <div className="bg-white/[0.03] rounded-xl p-4">
                    <div className="text-[10px] text-white/30 uppercase">
                      {t.features.transparency.balance}
                    </div>
                    <div className="text-2xl font-bold font-mono mt-1">€12,450</div>
                    <div className="text-xs text-emerald-400 mt-1">+24.5%</div>
                  </div>
                  <div className="bg-white/[0.03] rounded-xl p-4">
                    <div className="text-[10px] text-white/30 uppercase">
                      {t.features.transparency.today}
                    </div>
                    <div className="text-2xl font-bold font-mono mt-1">+€234</div>
                    <div className="text-xs text-emerald-400 mt-1">+1.92%</div>
                  </div>
                </div>
                <div className="bg-white/[0.02] rounded-xl p-4">
                  <div className="h-24 flex items-end gap-[3px]">
                    {[30,45,35,55,50,60,48,65,55,70,62,75,68,80,72,85,78,90,82,88,95,90,92,88,95,92,98,95,100].map((h, i) => (
                      <div
                        key={i}
                        className="flex-1 rounded-sm bg-gradient-to-t from-violet-500/20 to-violet-500/5"
                        style={{ height: `${h}%` }}
                      />
                    ))}
                  </div>
                </div>
              </div>
            </div>
          </RevealSection>
        </div>
      </section>

      {/* === PRICING === */}
      <section id="pricing" className="border-t border-white/5 bg-white/[0.01] py-32">
        <div className="max-w-5xl mx-auto px-8">
          <RevealSection className="text-center mb-20">
            <div className="text-xs uppercase tracking-widest text-white/30 mb-4">
              {t.pricing.label}
            </div>
            <h2 className="text-5xl md:text-6xl font-bold tracking-tight">
              {t.pricing.title}
            </h2>
          </RevealSection>

          <div className="grid md:grid-cols-3 gap-6">
            {(
              Object.entries(TIERS) as [
                string,
                (typeof TIERS)[keyof typeof TIERS],
              ][]
            ).map(([key, tier], i) => (
              <RevealSection key={key} delay={i * 100}>
                <div
                  className={`rounded-3xl p-10 h-full flex flex-col relative overflow-hidden ${
                    key === "pro"
                      ? "bg-gradient-to-b from-violet-500/10 to-fuchsia-500/5 border border-violet-500/20 shadow-[0_0_40px_rgba(139,92,246,0.1)]"
                      : "glass-card"
                  }`}
                >
                  {key === "pro" && (
                    <div className="absolute -top-3 left-1/2 -translate-x-1/2 px-4 py-1 bg-gradient-to-r from-violet-500 to-fuchsia-500 rounded-full text-xs font-semibold">
                      {t.pricing.recommended}
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
                    {t.pricing.then} {formatCurrency(tier.monthly)}
                    {t.pricing.perMonth}
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
                    href={isLoggedIn ? `/checkout?tier=${key}` : `/signup?tier=${key}`}
                    className={`w-full py-3.5 rounded-full font-semibold text-sm transition-all text-center block ${
                      key === "pro"
                        ? "bg-gradient-to-r from-violet-500 to-fuchsia-500 text-white hover:opacity-90"
                        : "bg-white/5 hover:bg-white/10 border border-white/10"
                    }`}
                  >
                    {t.pricing.getStarted}
                  </Link>
                </div>
              </RevealSection>
            ))}
          </div>
        </div>
      </section>

      {/* === FINAL CTA === */}
      <RevealSection>
        <section className="py-40 text-center px-8 relative">
          <div className="absolute bottom-0 left-1/3 w-[400px] h-[300px] bg-gradient-to-t from-violet-500/10 to-transparent blur-[100px]" />
          <div className="absolute bottom-0 right-1/3 w-[400px] h-[300px] bg-gradient-to-t from-fuchsia-500/[0.08] to-transparent blur-[100px]" />
          <div className="relative">
            <h2 className="text-5xl md:text-7xl font-bold tracking-tighter mb-8">
              {t.cta.line1}
              <br />
              <span className="text-white/30">{t.cta.line2}</span>
            </h2>
            <Link
              href={isLoggedIn ? "/pricing" : "/signup"}
              className="group inline-flex items-center gap-3 bg-gradient-to-r from-violet-500 to-fuchsia-500 text-white font-semibold px-10 py-4 rounded-full text-lg hover:shadow-[0_0_40px_rgba(139,92,246,0.3)] transition-all"
            >
              {t.cta.getStarted}
              <ArrowRight className="w-5 h-5 group-hover:translate-x-1 transition-transform" />
            </Link>
          </div>
        </section>
      </RevealSection>

      {/* Footer */}
      <footer className="border-t border-white/5 py-8">
        <div className="max-w-5xl mx-auto px-8 flex items-center justify-between text-xs text-white/15">
          <span>© 2026 CryptoBot</span>
          <div className="flex gap-6">
            <span className="hover:text-white/30 cursor-default">
              {t.footer.privacy}
            </span>
            <span className="hover:text-white/30 cursor-default">
              {t.footer.terms}
            </span>
            <span className="hover:text-white/30 cursor-default">
              {t.footer.support}
            </span>
          </div>
        </div>
      </footer>
    </div>
  );
}
