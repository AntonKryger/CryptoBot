import { Brain, Shield, Zap, BarChart3, Lock, Bell } from "lucide-react";

const FEATURES = [
  {
    icon: Brain,
    title: "AI Signal Engine",
    description:
      "Multi-model AI analyzes technicals, sentiment, and on-chain data",
  },
  {
    icon: Shield,
    title: "Risk Management",
    description:
      "ADX gates, R:R filters, and position sizing protect your capital",
  },
  {
    icon: Zap,
    title: "Instant Execution",
    description: "Sub-second trade execution on Capital.com CFDs",
  },
  {
    icon: BarChart3,
    title: "Live Dashboard",
    description: "Real-time P/L tracking, trade history, and bot health",
  },
  {
    icon: Lock,
    title: "Bank-Grade Security",
    description: "AES-256 encrypted API keys, 2FA, and isolated accounts",
  },
  {
    icon: Bell,
    title: "Telegram Alerts",
    description: "Get notified on every trade, signal, and account event",
  },
];

export default function Features() {
  return (
    <section className="relative px-6 py-24">
      <div className="max-w-6xl mx-auto">
        {/* Section header */}
        <div className="text-center mb-16">
          <h2 className="text-3xl sm:text-4xl font-bold text-text-primary mb-4">
            Everything You Need to{" "}
            <span className="text-gradient">Trade Smarter</span>
          </h2>
          <p className="text-text-secondary text-lg max-w-2xl mx-auto">
            A fully autonomous trading system with institutional-grade tools,
            built for the modern crypto trader.
          </p>
        </div>

        {/* Feature grid */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {FEATURES.map((feature) => {
            const Icon = feature.icon;
            return (
              <div
                key={feature.title}
                className="glass rounded-xl p-6 transition-all duration-200 hover:bg-bg-card-hover hover:border-border-hover group"
              >
                <div className="w-10 h-10 rounded-lg bg-accent-muted flex items-center justify-center mb-4">
                  <Icon className="w-5 h-5 text-accent" />
                </div>
                <h3 className="text-lg font-semibold text-text-primary mb-2 group-hover:text-gradient transition-colors">
                  {feature.title}
                </h3>
                <p className="text-sm text-text-secondary leading-relaxed">
                  {feature.description}
                </p>
              </div>
            );
          })}
        </div>
      </div>
    </section>
  );
}
