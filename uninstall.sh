#!/bin/bash

# Network Radar Uninstall Script
# اسکریپت حذف سرویس مانیتورینگ شبکه

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${RED}"
echo "╔══════════════════════════════════════════╗"
echo "║       Network Radar Uninstallation       ║"
echo "║       حذف سرویس مانیتورینگ شبکه          ║"
echo "╚══════════════════════════════════════════╝"
echo -e "${NC}"

if [ "$EUID" -ne 0 ]; then
    echo -e "${YELLOW}⚠️  Please run as root or with sudo${NC}"
    exit 1
fi

read -p "Are you sure you want to uninstall Network Radar? (y/N) " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "Cancelled."
    exit 0
fi

SERVICE_NAME="network-radar"
INSTALL_DIR="/opt/network-radar"
SERVICE_USER="radar"

echo -e "${BLUE}[1/4] Stopping service...${NC}"
systemctl stop $SERVICE_NAME 2>/dev/null || true
systemctl disable $SERVICE_NAME 2>/dev/null || true

echo -e "${BLUE}[2/4] Removing service file...${NC}"
rm -f /etc/systemd/system/$SERVICE_NAME.service
systemctl daemon-reload

echo -e "${BLUE}[3/4] Removing installation directory...${NC}"
rm -rf "$INSTALL_DIR"

echo -e "${BLUE}[4/4] Removing service user...${NC}"
userdel $SERVICE_USER 2>/dev/null || true

echo ""
echo -e "${GREEN}✓ Network Radar has been uninstalled successfully${NC}"
echo -e "${GREEN}✓ سرویس مانیتورینگ با موفقیت حذف شد${NC}"
echo ""
