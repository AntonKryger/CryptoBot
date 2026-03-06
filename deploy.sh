#!/bin/bash
# CryptoBot deploy script for Hetzner VPS
# Usage: ssh root@<SERVER_IP> 'bash -s' < deploy.sh

set -e

echo "=== CryptoBot Deploy ==="

# Update system
apt-get update && apt-get upgrade -y

# Install Docker
if ! command -v docker &> /dev/null; then
    echo "Installing Docker..."
    curl -fsSL https://get.docker.com | sh
    systemctl enable docker
    systemctl start docker
fi

# Install Docker Compose plugin
if ! docker compose version &> /dev/null; then
    apt-get install -y docker-compose-plugin
fi

# Clone repo
if [ ! -d "/opt/cryptobot" ]; then
    git clone https://github.com/AntonKryger/CryptoBot.git /opt/cryptobot
else
    cd /opt/cryptobot && git pull
fi

cd /opt/cryptobot

# Check config exists
if [ ! -f "config.yaml" ]; then
    echo ""
    echo "VIGTIGT: config.yaml mangler!"
    echo "Koer: nano /opt/cryptobot/config.yaml"
    echo "Og indsaet dine API credentials."
    echo ""
    cp config.example.yaml config.yaml
    exit 1
fi

# Build and start
docker compose up -d --build

echo ""
echo "=== CryptoBot kører! ==="
echo "Tjek status: docker compose logs -f"
echo "Stop: docker compose down"
echo "Genstart: docker compose restart"
