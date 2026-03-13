import { Check } from "lucide-react";
import { cn } from "@/lib/utils";
import { TIERS } from "@/lib/constants";

const TIER_KEYS = ["starter", "pro", "elite"] as const;

export default function PricingCards() {
  return (
    <section id="pricing" className="relative px-6 py-24">
      <div className="max-w-6xl mx-auto">
        {/* Section header */}
        <div className="text-center mb-16">
          <h2 className="text-3xl sm:text-4xl font-bold text-text-primary mb-4">
            Simple, Transparent{" "}
            <span className="text-gradient">Pricing</span>
          </h2>
          <p className="text-text-secondary text-lg max-w-xl mx-auto">
            One-time access fee plus affordable monthly hosting. No hidden fees,
            no revenue share.
          </p>
        </div>

        {/* Pricing grid */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6 max-w-5xl mx-auto">
          {TIER_KEYS.map((key) => {
            const tier = TIERS[key];
            const isPopular = key === "pro";

            return (
              <div
                key={key}
                className={cn(
                  "relative rounded-xl border p-8 flex flex-col transition-all duration-200",
                  isPopular
                    ? "bg-bg-card border-accent glow scale-[1.02]"
                    : "bg-bg-card border-border hover:border-border-hover hover:bg-bg-card-hover"
                )}
              >
                {/* Popular badge */}
                {isPopular && (
                  <div className="absolute -top-3 left-1/2 -translate-x-1/2">
                    <span className="inline-block px-4 py-1 rounded-full bg-accent text-white text-xs font-semibold tracking-wide uppercase">
                      Most Popular
                    </span>
                  </div>
                )}

                {/* Tier name */}
                <h3
                  className={cn(
                    "text-xl font-bold mb-6",
                    isPopular ? "text-gradient" : "text-text-primary"
                  )}
                >
                  {tier.name}
                </h3>

                {/* Pricing */}
                <div className="mb-2">
                  <span className="text-4xl font-bold text-text-primary font-mono">
                    &euro;{tier.oneTime}
                  </span>
                </div>
                <p className="text-sm text-text-muted mb-4">one-time access</p>

                <div className="mb-2">
                  <span className="text-2xl font-bold text-text-secondary font-mono">
                    &euro;{tier.monthly}
                  </span>
                  <span className="text-text-muted text-sm">/mo</span>
                </div>
                <p className="text-sm text-text-muted mb-8">bot hosting</p>

                {/* Features */}
                <ul className="space-y-3 mb-8 flex-1">
                  {tier.features.map((feature) => (
                    <li
                      key={feature}
                      className="flex items-start gap-3 text-sm"
                    >
                      <Check
                        className={cn(
                          "w-4 h-4 mt-0.5 flex-shrink-0",
                          isPopular ? "text-accent" : "text-success"
                        )}
                      />
                      <span className="text-text-secondary">{feature}</span>
                    </li>
                  ))}
                </ul>

                {/* CTA */}
                <a
                  href="#"
                  className={cn(
                    "inline-flex items-center justify-center h-11 rounded-lg font-semibold text-sm transition-all",
                    isPopular
                      ? "bg-accent text-white hover:bg-accent-hover hover:shadow-lg hover:shadow-accent/20"
                      : "border border-border text-text-primary hover:border-border-hover hover:bg-bg-card-hover"
                  )}
                >
                  Get Started
                </a>
              </div>
            );
          })}
        </div>
      </div>
    </section>
  );
}
