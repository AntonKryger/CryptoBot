export const THEMES = ["midnight", "matrix", "aurora", "stealth", "solar"] as const;
export type Theme = (typeof THEMES)[number];

export const THEME_LABELS: Record<Theme, string> = {
  midnight: "Midnight",
  matrix: "Matrix",
  aurora: "Aurora",
  stealth: "Stealth",
  solar: "Solar",
};

export const TIERS = {
  starter: {
    name: "Starter",
    oneTime: 149,
    monthly: 19,
    features: [
      "1 bot instance",
      "3 coin pairs",
      "Basic dashboard",
      "Email support",
    ],
  },
  pro: {
    name: "Pro",
    oneTime: 349,
    monthly: 39,
    features: [
      "3 bot instances",
      "All 6 coin pairs",
      "Advanced analytics",
      "Priority support",
      "Custom risk settings",
    ],
  },
  elite: {
    name: "Elite",
    oneTime: 799,
    monthly: 79,
    features: [
      "Unlimited bots",
      "All 6 coin pairs",
      "Full analytics suite",
      "Dedicated support",
      "Custom strategies",
      "API access",
    ],
  },
} as const;

export const ALLOWED_COINS = [
  "BTCUSD",
  "ETHUSD",
  "SOLUSD",
  "AVAXUSD",
  "LINKUSD",
  "LTCUSD",
] as const;
