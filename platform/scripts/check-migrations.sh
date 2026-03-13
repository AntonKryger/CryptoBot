#!/usr/bin/env bash
# Checks that migration files are sequentially numbered without gaps.
# Usage: bash scripts/check-migrations.sh

set -euo pipefail

MIGRATIONS_DIR="supabase/migrations"

if [ ! -d "$MIGRATIONS_DIR" ]; then
  echo "Error: $MIGRATIONS_DIR directory not found."
  exit 1
fi

echo "Checking migration numbering in $MIGRATIONS_DIR/..."
echo ""

# Extract migration numbers, sort them
NUMBERS=()
for file in "$MIGRATIONS_DIR"/*.sql; do
  [ -f "$file" ] || continue
  basename=$(basename "$file")
  # Extract leading digits (e.g., 001 from 001_initial_schema.sql)
  num=$(echo "$basename" | grep -oE '^[0-9]+')
  if [ -z "$num" ]; then
    echo "  WARNING: $basename has no numeric prefix"
    continue
  fi
  NUMBERS+=("$num")
  echo "  Found: $basename (number: $num)"
done

echo ""

if [ ${#NUMBERS[@]} -eq 0 ]; then
  echo "No migrations found."
  exit 0
fi

# Sort numerically
IFS=$'\n' SORTED=($(sort -n <<<"${NUMBERS[*]}")); unset IFS

# Check for gaps
EXPECTED=1
GAPS=0
for num in "${SORTED[@]}"; do
  actual=$((10#$num))
  if [ "$actual" -ne "$EXPECTED" ]; then
    echo "  GAP: Expected $(printf '%03d' $EXPECTED), found $(printf '%03d' $actual)"
    GAPS=$((GAPS + 1))
  fi
  EXPECTED=$((actual + 1))
done

if [ "$GAPS" -gt 0 ]; then
  echo "Result: $GAPS gap(s) found in migration numbering."
  exit 1
else
  echo "Result: All ${#NUMBERS[@]} migration(s) numbered sequentially."
  exit 0
fi
