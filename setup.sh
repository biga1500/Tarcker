#!/usr/bin/env bash
# setup.sh — Instalação completa do Tarcker no Linux
set -e

WORK_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON="${PYTHON:-python3}"
SERVICE_DIR="$HOME/.config/systemd/user"

echo "======================================================"
echo "  Tarcker — Instalação"
echo "  Diretório: $WORK_DIR"
echo "======================================================"
echo ""

# ------------------------------------------------------------------
# 1. Dependências de sistema
# ------------------------------------------------------------------
echo "▸ Instalando dependências do sistema..."
if command -v apt-get &>/dev/null; then
    sudo apt-get install -y --no-install-recommends \
        xdotool xprintidle libnotify-bin python3-pip python3-tk 2>/dev/null || true
elif command -v dnf &>/dev/null; then
    sudo dnf install -y xdotool libnotify python3-pip 2>/dev/null || true
elif command -v pacman &>/dev/null; then
    sudo pacman -S --noconfirm xdotool xorg-xprintidle libnotify python-pip 2>/dev/null || true
else
    echo "  AVISO: Instale manualmente: xdotool, xprintidle, libnotify"
fi

# ------------------------------------------------------------------
# 2. Dependências Python
# ------------------------------------------------------------------
echo "▸ Instalando dependências Python..."
"$PYTHON" -m pip install --quiet --upgrade pip
"$PYTHON" -m pip install --quiet \
    psutil pynput Pillow plyer pystray

# ------------------------------------------------------------------
# 3. Criar config padrão
# ------------------------------------------------------------------
echo "▸ Criando configuração padrão..."
"$PYTHON" -c "from tarcker.config import load_config; load_config()" 2>/dev/null || true
CONFIG_FILE="$HOME/.tarcker/config.json"
echo "  Configuração em: $CONFIG_FILE"

# ------------------------------------------------------------------
# 4. Serviço systemd do usuário
# ------------------------------------------------------------------
echo "▸ Instalando serviço systemd..."
mkdir -p "$SERVICE_DIR"

# Descobre o UID real para o bus do D-Bus
REAL_UID=$(id -u)

cat > "$SERVICE_DIR/tarcker.service" <<EOF
[Unit]
Description=Tarcker — monitor de atividade pessoal
After=graphical-session.target

[Service]
Type=simple
ExecStart=$PYTHON $WORK_DIR/main.py --no-log
WorkingDirectory=$WORK_DIR
Restart=on-failure
RestartSec=10

Environment=DISPLAY=:0
Environment=XAUTHORITY=%h/.Xauthority
Environment=DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/${REAL_UID}/bus
Environment=XDG_RUNTIME_DIR=/run/user/${REAL_UID}

StandardOutput=journal
StandardError=journal
SyslogIdentifier=tarcker

[Install]
WantedBy=graphical-session.target
EOF

# Recarrega systemd do usuário
systemctl --user daemon-reload

# ------------------------------------------------------------------
# 5. Habilitar na inicialização
# ------------------------------------------------------------------
systemctl --user enable tarcker
echo "  Serviço habilitado — iniciará automaticamente com o login."

# Habilita linger para o serviço rodar mesmo sem terminal aberto
loginctl enable-linger "$USER" 2>/dev/null && \
    echo "  loginctl linger ativado." || \
    echo "  AVISO: 'loginctl enable-linger' falhou — tudo bem, serviço ainda funcionará após login."

# ------------------------------------------------------------------
# 6. Iniciar agora
# ------------------------------------------------------------------
echo ""
read -r -p "Iniciar o Tarcker agora? [S/n] " RESP
RESP="${RESP:-S}"
if [[ "$RESP" =~ ^[Ss]$ ]]; then
    systemctl --user start tarcker
    sleep 2
    STATUS=$(systemctl --user is-active tarcker 2>/dev/null || echo "unknown")
    if [ "$STATUS" = "active" ]; then
        echo "  ✓ Tarcker rodando em background!"
    else
        echo "  ✗ Falhou ao iniciar. Veja os logs:"
        echo "    journalctl --user -u tarcker -n 30"
    fi
fi

# ------------------------------------------------------------------
echo ""
echo "======================================================"
echo "  Instalação concluída!"
echo ""
echo "  Comandos úteis:"
echo "    status : systemctl --user status tarcker"
echo "    logs   : journalctl --user -u tarcker -f"
echo "    parar  : systemctl --user stop tarcker"
echo "    resumo : $PYTHON $WORK_DIR/main.py --summary"
echo "======================================================"
