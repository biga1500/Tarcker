#!/usr/bin/env bash
# setup.sh — Quick setup for Tarcker on Linux (Debian/Ubuntu)
set -e

echo "=== Tarcker Setup ==="

# 1. System dependencies
if command -v apt-get &>/dev/null; then
    echo "Instalando dependências (xdotool, xprintidle)..."
    sudo apt-get install -y xdotool xprintidle libnotify-bin
elif command -v dnf &>/dev/null; then
    sudo dnf install -y xdotool libnotify
elif command -v pacman &>/dev/null; then
    sudo pacman -S --noconfirm xdotool xorg-xprintidle libnotify
else
    echo "AVISO: Instale manualmente: xdotool, xprintidle, libnotify"
fi

# 2. Create config with first-run defaults
python3 -c "from tarcker.config import load_config; load_config()"
CONFIG_FILE="$HOME/.tarcker/config.json"
echo "Configuração salva em: $CONFIG_FILE"
echo ""
echo "Para ativar e-mail, edite $CONFIG_FILE e preencha a seção 'email'."

# 3. Systemd user service (optional)
SERVICE_DIR="$HOME/.config/systemd/user"
mkdir -p "$SERVICE_DIR"
WORK_DIR="$(pwd)"

cat > "$SERVICE_DIR/tarcker.service" <<EOF
[Unit]
Description=Tarcker Activity Monitor
After=graphical-session.target

[Service]
Type=simple
ExecStart=/usr/bin/python3 $WORK_DIR/main.py
Restart=on-failure
RestartSec=10
Environment=DISPLAY=:0
Environment=DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/%U/bus

[Install]
WantedBy=default.target
EOF

echo "Serviço systemd criado em $SERVICE_DIR/tarcker.service"
echo ""
echo "Para habilitar na inicialização:"
echo "  systemctl --user daemon-reload"
echo "  systemctl --user enable --now tarcker"
echo ""
echo "=== Pronto! ==="
echo "Executar agora: python3 main.py"
