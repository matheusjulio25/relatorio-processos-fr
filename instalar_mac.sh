#!/bin/bash
# ============================================================
# INSTALADOR — Relatório Diário de Processos
# Fernandes & Rego Advogados Associados
# ============================================================
# Execute uma vez no Terminal:
#   cd ~/Documents/relatorio_processos
#   chmod +x instalar_mac.sh && ./instalar_mac.sh
# ============================================================

set -e

VERDE="\033[0;32m"
AMARELO="\033[1;33m"
VERMELHO="\033[0;31m"
RESET="\033[0m"

ok()   { echo -e "${VERDE}✓ $1${RESET}"; }
aviso(){ echo -e "${AMARELO}⚠ $1${RESET}"; }
erro() { echo -e "${VERMELHO}✗ $1${RESET}"; exit 1; }

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo ""
echo "============================================================"
echo "  Instalando: Relatório Diário de Processos — F&R"
echo "============================================================"
echo ""

# ── 1. Localiza o Python 3 ────────────────────────────────────
echo "[ 1/6 ] Verificando Python 3..."
PYTHON=""
for cmd in python3 python3.13 python3.12 python3.11 python3.10 python3.9; do
  if command -v "$cmd" &>/dev/null; then
    PYTHON="$cmd"
    break
  fi
done

if [ -z "$PYTHON" ]; then
  aviso "Python 3 não encontrado."
  echo "  Instale em: https://www.python.org/downloads/"
  echo "  Após instalar, rode este script novamente."
  exit 1
fi
ok "Python encontrado: $($PYTHON --version)"

# ── 2. Verifica Node.js ───────────────────────────────────────
echo "[ 2/6 ] Verificando Node.js..."
if ! command -v node &>/dev/null; then
  aviso "Node.js não encontrado."
  echo "  Instale em: https://nodejs.org/  (baixe a versão LTS)"
  echo "  Após instalar, rode este script novamente."
  exit 1
fi
NODE_DIR="$(dirname "$(command -v node)")"
ok "Node.js encontrado: $(node --version) em $NODE_DIR"

# ── 3. Cria ambiente virtual Python (necessário no macOS 3.12+) ──
echo "[ 3/6 ] Criando ambiente virtual Python (venv)..."
VENV_DIR="$SCRIPT_DIR/.venv"
if [ ! -d "$VENV_DIR" ]; then
  $PYTHON -m venv "$VENV_DIR"
fi
PYTHON_VENV="$VENV_DIR/bin/python"
ok "Ambiente virtual em: $VENV_DIR"

# ── 4. Instala dependências Python ───────────────────────────
echo "[ 4/6 ] Instalando dependências Python..."
"$PYTHON_VENV" -m pip install --quiet --upgrade pip
"$PYTHON_VENV" -m pip install --quiet python-dotenv notion-client
ok "Dependências Python instaladas."

# ── 5. Instala dependências Node ─────────────────────────────
echo "[ 5/6 ] Instalando dependências Node.js..."
cd "$SCRIPT_DIR"
npm install --silent docx
ok "Dependência 'docx' instalada."

# ── 6. Configura o agendamento (launchd) ─────────────────────
echo "[ 6/6 ] Configurando agendamento às 7h no macOS..."

PLIST_NAME="br.adv.fernandeserego.relatorio-diario"
PLIST_PATH="$HOME/Library/LaunchAgents/${PLIST_NAME}.plist"
LOG_DIR="$HOME/Library/Logs/RelatorioFR"
mkdir -p "$LOG_DIR"

# Inclui o diretório do Node no PATH do launchd
LAUNCH_PATH="/usr/local/bin:/usr/bin:/bin:/opt/homebrew/bin:${NODE_DIR}"

cat > "$PLIST_PATH" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>${PLIST_NAME}</string>

    <key>ProgramArguments</key>
    <array>
        <string>${PYTHON_VENV}</string>
        <string>${SCRIPT_DIR}/relatorio_diario.py</string>
    </array>

    <key>WorkingDirectory</key>
    <string>${SCRIPT_DIR}</string>

    <key>StartCalendarInterval</key>
    <dict>
        <key>Hour</key>
        <integer>7</integer>
        <key>Minute</key>
        <integer>0</integer>
    </dict>

    <key>StandardOutPath</key>
    <string>${LOG_DIR}/relatorio.log</string>

    <key>StandardErrorPath</key>
    <string>${LOG_DIR}/relatorio_erro.log</string>

    <key>RunAtLoad</key>
    <false/>

    <key>EnvironmentVariables</key>
    <dict>
        <key>PATH</key>
        <string>${LAUNCH_PATH}</string>
    </dict>
</dict>
</plist>
PLIST

# Usa sintaxe moderna do launchctl (macOS 10.15+)
PLIST_DOMAIN="gui/$(id -u)"
launchctl bootout "${PLIST_DOMAIN}/${PLIST_NAME}" 2>/dev/null || true
launchctl bootstrap "${PLIST_DOMAIN}" "$PLIST_PATH"
launchctl enable "${PLIST_DOMAIN}/${PLIST_NAME}"
ok "Agendamento configurado: todo dia às 7h00."

# ── Verifica .env ─────────────────────────────────────────────
echo ""
if [ ! -f "$SCRIPT_DIR/.env" ]; then
  aviso ".env não encontrado! Configure as credenciais:"
  echo ""
  echo "  cp '$SCRIPT_DIR/.env.example' '$SCRIPT_DIR/.env'"
  echo "  open '$SCRIPT_DIR/.env'"
  echo ""
  echo "  Preencha as senhas e salve. Depois teste com:"
  echo "  '$PYTHON_VENV' '$SCRIPT_DIR/relatorio_diario.py'"
else
  ok ".env encontrado."
fi

# ── Resumo final ──────────────────────────────────────────────
echo ""
echo "============================================================"
echo -e "${VERDE}  Instalação concluída com sucesso!${RESET}"
echo "============================================================"
echo ""
echo "  Pasta dos scripts : $SCRIPT_DIR"
echo "  Relatórios gerados: $SCRIPT_DIR/Relatorio_Diario_*.docx"
echo "  Logs              : $LOG_DIR/"
echo "  Próxima execução  : amanhã às 7h00"
echo ""
echo "  Para testar agora:"
echo "  cd '$SCRIPT_DIR' && '$PYTHON_VENV' relatorio_diario.py"
echo ""
