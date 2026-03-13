#!/usr/bin/env bash
# Validates that all required environment variables are set.
# Usage: bash scripts/validate-env.sh

set -euo pipefail

REQUIRED_VARS=(
  "NEXT_PUBLIC_SUPABASE_URL"
  "NEXT_PUBLIC_SUPABASE_ANON_KEY"
  "SUPABASE_SERVICE_ROLE_KEY"
  "ENCRYPTION_KEY"
  "STRIPE_SECRET_KEY"
  "STRIPE_PUBLISHABLE_KEY"
  "STRIPE_WEBHOOK_SECRET"
  "SYNC_SECRET"
)

ENV_FILE=".env.local"
MISSING=0

echo "Checking environment variables..."
echo ""

for var in "${REQUIRED_VARS[@]}"; do
  # Check .env.local if it exists
  if [ -f "$ENV_FILE" ]; then
    value=$(grep "^${var}=" "$ENV_FILE" 2>/dev/null | cut -d '=' -f2- || true)
  else
    value=""
  fi

  # Fall back to actual env
  if [ -z "$value" ]; then
    value="${!var:-}"
  fi

  if [ -z "$value" ] || [ "$value" = "" ]; then
    echo "  MISSING: $var"
    MISSING=$((MISSING + 1))
  elif [[ "$value" == *"placeholder"* ]]; then
    echo "  PLACEHOLDER: $var (set but contains 'placeholder')"
  else
    echo "  OK: $var"
  fi
done

echo ""
if [ "$MISSING" -gt 0 ]; then
  echo "Result: $MISSING required variable(s) missing."
  exit 1
else
  echo "Result: All required variables are set."
  exit 0
fi
