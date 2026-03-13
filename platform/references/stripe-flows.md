# Stripe Flows Reference

## To-lags betalingsmodel

| Lag | Type | Beloeb | Stripe metode |
|-----|------|--------|---------------|
| 1 | Engangsbetaling | Starter €149 / Pro €349 / Elite €799 | Payment Intent |
| 2 | Maanedligt abonnement | Starter €19 / Pro €39 / Elite €79 | Subscription |

Abonnement oprettes EFTER engangsbetaling er gennemfoert.

## Flow

```
Bruger vaelger tier paa /pricing
  → POST /api/stripe/create-payment (Payment Intent med metadata: user_id, tier)
  → Stripe Elements betalingsform
  → payment_intent.succeeded webhook
    → profiles.role = 'subscriber', profiles.tier = tier
    → POST /api/stripe/create-subscription (automatic)
    → Redirect til /onboarding
```

## Webhook Events

| Event | Handling |
|-------|---------|
| `payment_intent.succeeded` | Saet `role = 'subscriber'`, saet `tier`, opret subscription |
| `invoice.paid` | Clear grace period, resume bot, `subscription_status = 'active'` |
| `invoice.payment_failed` | `grace_period_ends_at = now() + 3 dage`, `subscription_status = 'past_due'`, send Telegram besked |
| `customer.subscription.deleted` | Suspend alle brugerens bots, `subscription_status = 'canceled'` |

## Grace Period

- 3 dage efter mislykket betaling
- pgcron checker hver 6. time (uafhaengig af Python)
- Naar grace period udloeber: `is_suspended = true` paa alle brugerens bots
- Bruger kan genaktivere ved at betale

## Env vars (placeholders til start)

```
STRIPE_SECRET_KEY=sk_test_placeholder
STRIPE_PUBLISHABLE_KEY=pk_test_placeholder
STRIPE_WEBHOOK_SECRET=whsec_placeholder
STRIPE_STARTER_PRICE_ID=
STRIPE_PRO_PRICE_ID=
STRIPE_ELITE_PRICE_ID=
```

Price IDs oprettes i Stripe Dashboard → Products → Prices.

## Sikkerhed

- Aldrig gem card details — Stripe haandterer alt
- Webhook signatur verification med `STRIPE_WEBHOOK_SECRET`
- Idempotency keys paa alle mutations (undgaa duplicate charges)
- Amount verification: server checker at amount matcher tier (klienten kan ikke override)
