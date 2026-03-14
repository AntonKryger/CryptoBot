#!/bin/bash
# Deploy a batch of bot variants to the VPS
# Usage: ./scripts/deploy_batch.sh [--batch A] [--dry-run]

set -e

BATCH=""
DRY_RUN=false

while [[ $# -gt 0 ]]; do
    case $1 in
        --batch) BATCH="$2"; shift 2 ;;
        --dry-run) DRY_RUN=true; shift ;;
        *) echo "Unknown option: $1"; exit 1 ;;
    esac
done

echo "============================================"
echo "  CryptoBot Variant Deployment"
echo "============================================"

# Step 1: Generate configs
echo ""
echo "[1/4] Generating variant configs..."
if [ -n "$BATCH" ]; then
    python scripts/generate_variant.py --batch "$BATCH"
else
    python scripts/generate_variant.py
fi

# Step 2: Preflight check
echo ""
echo "[2/4] Running preflight check..."
python preflight_check.py
if [ $? -ne 0 ]; then
    echo "Preflight check failed! Fix credential conflicts before deploying."
    exit 1
fi

if [ "$DRY_RUN" = true ]; then
    echo ""
    echo "[DRY-RUN] Would push to git and rebuild on VPS."
    exit 0
fi

# Step 3: Push to git
echo ""
echo "[3/4] Pushing to git..."
git add -A
git commit -m "Deploy variant batch${BATCH:+ $BATCH}" || echo "Nothing to commit"
git push origin master

# Step 4: SSH to VPS and rebuild
echo ""
echo "[4/4] Rebuilding on VPS..."
ssh -i ~/.ssh/id_ed25519 root@91.98.26.70 << 'EOF'
cd /root/cryptobot
git pull origin master
docker compose -f docker-compose.generated.yml down
docker compose -f docker-compose.generated.yml up -d --build
echo ""
echo "Containers running:"
docker ps --format "table {{.Names}}\t{{.Status}}" | grep cryptobot
EOF

echo ""
echo "============================================"
echo "  Deployment complete!"
echo "============================================"
