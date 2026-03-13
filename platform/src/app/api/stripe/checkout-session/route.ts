import { NextRequest, NextResponse } from "next/server";
import { stripe } from "@/lib/stripe/server";
import { createServerSupabaseClient } from "@/lib/supabase/server";
import { STRIPE_PLANS } from "@/lib/stripe/plans";
import { TIERS } from "@/lib/constants";
import type { Tier } from "@/lib/supabase/types";

export async function POST(req: NextRequest) {
  try {
    // Check Stripe keys are configured
    if (!process.env.STRIPE_SECRET_KEY) {
      return NextResponse.json(
        {
          error:
            "Stripe is not configured. Set STRIPE_SECRET_KEY in your environment variables.",
        },
        { status: 500 }
      );
    }

    // Parse body
    const body = await req.json();
    const tier = body.tier as Tier;

    // Validate tier
    if (!tier || !(tier in TIERS)) {
      return NextResponse.json(
        { error: "Invalid tier. Must be one of: starter, pro, elite." },
        { status: 400 }
      );
    }

    // Verify user is authenticated
    const supabase = createServerSupabaseClient();
    const {
      data: { user },
    } = await supabase.auth.getUser();

    if (!user) {
      return NextResponse.json(
        { error: "You must be logged in to checkout." },
        { status: 401 }
      );
    }

    const plan = STRIPE_PLANS[tier];
    const tierInfo = TIERS[tier];

    // Check that monthly price ID is configured
    if (!plan.monthlyPriceId) {
      return NextResponse.json(
        {
          error: `Stripe price ID for ${tierInfo.name} is not configured. Set STRIPE_${tier.toUpperCase()}_PRICE_ID in your environment variables.`,
        },
        { status: 500 }
      );
    }

    // Build the base URL for redirects
    const origin = req.headers.get("origin") || "http://localhost:3000";

    // Create Stripe Checkout Session in subscription mode.
    // The one-time setup fee is added via invoice_settings on the first invoice.
    const session = await stripe.checkout.sessions.create({
      mode: "subscription",
      line_items: [
        {
          price: plan.monthlyPriceId,
          quantity: 1,
        },
      ],
      subscription_data: {
        metadata: {
          tier,
          user_id: user.id,
        },
      },
      payment_method_types: ["card"],
      success_url: `${origin}/dashboard?checkout=success`,
      cancel_url: `${origin}/pricing`,
      client_reference_id: user.id,
      customer_email: user.email,
      metadata: {
        tier,
        user_id: user.id,
        setup_fee_amount: plan.oneTimeAmount.toString(),
        setup_fee_description: `${tierInfo.name} Plan - One-time setup fee`,
      },
    });

    // If the session created a customer, add the one-time setup fee
    // as an invoice item that will be charged on the first subscription invoice.
    if (session.customer) {
      await stripe.invoiceItems.create({
        customer: session.customer as string,
        amount: plan.oneTimeAmount,
        currency: "eur",
        description: `${tierInfo.name} Plan - One-time setup fee`,
      });
    }

    return NextResponse.json({ url: session.url });
  } catch (error) {
    console.error("Stripe checkout session error:", error);
    const message =
      error instanceof Error ? error.message : "Internal server error";
    return NextResponse.json({ error: message }, { status: 500 });
  }
}
