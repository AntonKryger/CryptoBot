import { cn } from "@/lib/utils";

const MOCK_TRADES = [
  { pair: "BTC/USD", price: "67,842.50", change: "+2.34%", positive: true },
  { pair: "ETH/USD", price: "3,521.18", change: "+1.12%", positive: true },
  { pair: "SOL/USD", price: "142.67", change: "-0.45%", positive: false },
  { pair: "LINK/USD", price: "18.94", change: "+3.21%", positive: true },
  { pair: "LTC/USD", price: "84.32", change: "+0.67%", positive: true },
];

const STATS = [
  { value: "6", label: "Coins" },
  { value: "24/7", label: "Trading" },
  { value: "AI", label: "Driven" },
];

export default function Hero() {
  return (
    <section className="relative min-h-screen flex flex-col items-center justify-center px-6 pt-24 pb-16 overflow-hidden">
      {/* Background glow effects */}
      <div className="absolute top-1/4 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[600px] h-[600px] rounded-full bg-accent/5 blur-[120px] pointer-events-none" />
      <div className="absolute bottom-1/4 right-1/4 w-[400px] h-[400px] rounded-full bg-accent/3 blur-[100px] pointer-events-none" />

      <div className="relative z-10 max-w-5xl mx-auto text-center">
        {/* Headline */}
        <h1 className="text-5xl sm:text-6xl lg:text-7xl font-bold tracking-tight leading-tight mb-6">
          <span className="text-gradient">AI-Powered</span>{" "}
          <span className="text-text-primary">Crypto Trading</span>
        </h1>

        {/* Subheadline */}
        <p className="text-lg sm:text-xl text-text-secondary max-w-2xl mx-auto mb-10 leading-relaxed">
          Autonomous trading bot on your Capital.com account. Set up in minutes,
          profit 24/7.
        </p>

        {/* CTA Buttons */}
        <div className="flex flex-col sm:flex-row items-center justify-center gap-4 mb-16">
          <a
            href="#pricing"
            className="inline-flex items-center justify-center h-12 px-8 rounded-lg bg-accent text-white font-semibold text-base transition-all hover:bg-accent-hover hover:shadow-lg hover:shadow-accent/20"
          >
            Get Started
          </a>
          <a
            href="#pricing"
            className="inline-flex items-center justify-center h-12 px-8 rounded-lg border border-border text-text-primary font-semibold text-base transition-all hover:border-border-hover hover:bg-bg-card"
          >
            See Pricing
          </a>
        </div>

        {/* Mock Terminal Card */}
        <div className="glass rounded-xl p-1 max-w-2xl mx-auto mb-12">
          {/* Terminal header */}
          <div className="flex items-center gap-2 px-4 py-3 border-b border-border">
            <div className="w-3 h-3 rounded-full bg-danger/60" />
            <div className="w-3 h-3 rounded-full bg-warning/60" />
            <div className="w-3 h-3 rounded-full bg-success/60" />
            <span className="ml-3 text-xs text-text-muted font-mono">
              live-trades.sh
            </span>
          </div>

          {/* Trade rows */}
          <div className="p-4 space-y-2">
            {MOCK_TRADES.map((trade) => (
              <div
                key={trade.pair}
                className="flex items-center justify-between py-2 px-3 rounded-lg hover:bg-bg-card-hover/50 transition-colors"
              >
                <div className="flex items-center gap-3">
                  <div
                    className={cn(
                      "w-2 h-2 rounded-full",
                      trade.positive ? "bg-success" : "bg-danger"
                    )}
                  />
                  <span className="font-mono text-sm text-text-primary font-medium">
                    {trade.pair}
                  </span>
                </div>
                <div className="flex items-center gap-6">
                  <span className="font-mono text-sm text-text-secondary">
                    ${trade.price}
                  </span>
                  <span
                    className={cn(
                      "font-mono text-sm font-medium min-w-[70px] text-right",
                      trade.positive ? "text-success" : "text-danger"
                    )}
                  >
                    {trade.change}
                  </span>
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Floating Stats */}
        <div className="flex items-center justify-center gap-8 sm:gap-16">
          {STATS.map((stat) => (
            <div key={stat.label} className="text-center">
              <div className="text-2xl sm:text-3xl font-bold text-gradient">
                {stat.value}
              </div>
              <div className="text-sm text-text-muted mt-1">{stat.label}</div>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
