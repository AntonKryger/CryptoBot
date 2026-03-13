export const STRIPE_PLANS = {
  starter: {
    oneTimeAmount: 14900, // €149 in cents
    monthlyPriceId: process.env.STRIPE_STARTER_PRICE_ID || "",
  },
  pro: {
    oneTimeAmount: 34900, // €349 in cents
    monthlyPriceId: process.env.STRIPE_PRO_PRICE_ID || "",
  },
  elite: {
    oneTimeAmount: 79900, // €799 in cents
    monthlyPriceId: process.env.STRIPE_ELITE_PRICE_ID || "",
  },
} as const;
