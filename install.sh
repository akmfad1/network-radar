#!/bin/bash

# Network Radar Installation Script
# اسکریپت نصب سرویس مانیتورینگ شبکه

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}"
echo "╔══════════════════════════════════════════╗"
echo "║       Network Radar Installation         ║"
echo "║       نصب سرویس مانیتورینگ شبکه          ║"
echo "╚══════════════════════════════════════════╝"
echo -e "${NC}"

# Check if running as root
if [ "$EUID" -ne 0 ]; then
    echo -e "${YELLOW}⚠️  Please run as root or with sudo${NC}"
    echo -e "${YELLOW}⚠️  لطفاً با دسترسی root یا sudo اجرا کنید${NC}"
    exit 1
fi

# Variables
INSTALL_DIR="/opt/network-radar"
SERVICE_USER="radar"
SERVICE_NAME="network-radar"
VENV_DIR="$INSTALL_DIR/venv"

echo -e "${BLUE}[1/7] Installing system dependencies...${NC}"
echo -e "${BLUE}[1/7] نصب وابستگی‌های سیستمی...${NC}"

# Detect package manager and install dependencies
if command -v apt-get &> /dev/null; then
    apt-get update -qq
    apt-get install -y -qq python3 python3-pip python3-venv iputils-ping dnsutils curl
elif command -v yum &> /dev/null; then
    yum install -y -q python3 python3-pip iputils bind-utils curl
elif command -v dnf &> /dev/null; then
    dnf install -y -q python3 python3-pip iputils bind-utils curl
elif command -v pacman &> /dev/null; then
    pacman -Sy --noconfirm python python-pip iputils bind-tools curl
else
    echo -e "${RED}❌ Unsupported package manager${NC}"
    exit 1
fi

echo -e "${GREEN}✓ System dependencies installed${NC}"

echo -e "${BLUE}[2/7] Creating service user...${NC}"
echo -e "${BLUE}[2/7] ایجاد کاربر سرویس...${NC}"

# Create service user if not exists
if ! id "$SERVICE_USER" &>/dev/null; then
    useradd -r -s /bin/false -d "$INSTALL_DIR" "$SERVICE_USER"
    echo -e "${GREEN}✓ User '$SERVICE_USER' created${NC}"
else
    echo -e "${YELLOW}User '$SERVICE_USER' already exists${NC}"
fi

echo -e "${BLUE}[3/7] Setting up installation directory...${NC}"
echo -e "${BLUE}[3/7] آماده‌سازی دایرکتوری نصب...${NC}"

# Create installation directory
mkdir -p "$INSTALL_DIR"

# Copy application files
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cp -r "$SCRIPT_DIR"/* "$INSTALL_DIR/"
rm -f "$INSTALL_DIR/install.sh"  # Remove installer from target

echo -e "${GREEN}✓ Application files copied${NC}"

echo -e "${BLUE}[4/7] Creating Python virtual environment...${NC}"
echo -e "${BLUE}[4/7] ایجاد محیط مجازی پایتون...${NC}"

# Create virtual environment
python3 -m venv "$VENV_DIR"

echo -e "${GREEN}✓ Virtual environment created${NC}"

echo -e "${BLUE}[5/7] Installing Python dependencies...${NC}"
echo -e "${BLUE}[5/7] نصب وابستگی‌های پایتون...${NC}"

# Install Python dependencies
"$VENV_DIR/bin/pip" install --upgrade pip -q
"$VENV_DIR/bin/pip" install -r "$INSTALL_DIR/requirements.txt" -q

echo -e "${GREEN}✓ Python dependencies installed${NC}"

echo -e "${BLUE}[6/7] Creating systemd service...${NC}"
echo -e "${BLUE}[6/7] ایجاد سرویس systemd...${NC}"

# Create systemd service file
cat > /etc/systemd/system/$SERVICE_NAME.service << EOF
[Unit]
Description=Network Radar - Connection Monitoring Service
After=network.target

[Service]
Type=simple
User=$SERVICE_USER
Group=$SERVICE_USER
WorkingDirectory=$INSTALL_DIR
Environment="PATH=$VENV_DIR/bin"
ExecStart=$VENV_DIR/bin/python app.py
Restart=always
RestartSec=10

# Security hardening
NoNewPrivileges=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=$INSTALL_DIR

[Install]
WantedBy=multi-user.target
EOF

# Set permissions
chown -R "$SERVICE_USER:$SERVICE_USER" "$INSTALL_DIR"
chmod -R 755 "$INSTALL_DIR"
chmod 644 /etc/systemd/system/$SERVICE_NAME.service

# Reload systemd
systemctl daemon-reload

echo -e "${GREEN}✓ Systemd service created${NC}"

echo -e "${BLUE}[7/7] Starting service...${NC}"
echo -e "${BLUE}[7/7] راه‌اندازی سرویس...${NC}"

# Enable and start service
systemctl enable $SERVICE_NAME
systemctl start $SERVICE_NAME

# Wait a moment for service to start
sleep 3

# Check service status
if systemctl is-active --quiet $SERVICE_NAME; then
    echo -e "${GREEN}✓ Service started successfully${NC}"
else
    echo -e "${RED}❌ Service failed to start. Check logs with: journalctl -u $SERVICE_NAME${NC}"
    exit 1
fi

echo ""
echo -e "${GREEN}╔══════════════════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║              Installation Complete! ✓                        ║${NC}"
echo -e "${GREEN}║              نصب با موفقیت انجام شد! ✓                       ║${NC}"
echo -e "${GREEN}╚══════════════════════════════════════════════════════════════╝${NC}"
echo ""
echo -e "${BLUE}📍 Dashboard URL:${NC} http://YOUR_SERVER_IP:5000"
echo -e "${BLUE}📍 آدرس داشبورد:${NC} http://YOUR_SERVER_IP:5000"
echo ""
echo -e "${BLUE}📁 Installation directory:${NC} $INSTALL_DIR"
echo -e "${BLUE}📁 دایرکتوری نصب:${NC} $INSTALL_DIR"
echo ""
echo -e "${BLUE}⚙️  Configuration file:${NC} $INSTALL_DIR/config.yaml"
echo -e "${BLUE}⚙️  فایل تنظیمات:${NC} $INSTALL_DIR/config.yaml"
echo ""
echo -e "${YELLOW}Useful Commands / دستورات مفید:${NC}"
echo -e "  ${BLUE}systemctl status $SERVICE_NAME${NC}    - Check service status"
echo -e "  ${BLUE}systemctl restart $SERVICE_NAME${NC}   - Restart service"
echo -e "  ${BLUE}systemctl stop $SERVICE_NAME${NC}      - Stop service"
echo -e "  ${BLUE}journalctl -u $SERVICE_NAME -f${NC}    - View logs"
echo ""
echo -e "${YELLOW}⚠️  Don't forget to configure your firewall:${NC}"
echo -e "  ${BLUE}ufw allow 5000${NC}  or  ${BLUE}firewall-cmd --add-port=5000/tcp --permanent${NC}"
echo ""
