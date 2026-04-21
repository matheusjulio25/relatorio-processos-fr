#!/bin/bash
# ============================================================
# INSTALADOR — Relatório Diário de Processos
# Fernandes & Rego Advogados Associados
# ============================================================
# Execute uma vez no Terminal:
#   cd ~/Downloads/relatorio_processos
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

echo ""
echo "============================================================"
echo "  Instalando: Relatório Diário de Processos — F&R"
echo "============================================================"
echo ""

# ── 1. Localiza o Python 3 ────────────────────────────────────
echo "[ 1/5 ] Verificando Python 3..."
PYTHON=""
for cmd in python3 python3.12 python3.11 python3.10 python3.9; do
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
echo "[ 2/5 ] Verificando Node.js..."
if ! command -v node &>/dev/null; then
  aviso "Node.js não encontrado."
  echo "  Instale em: https://nodejs.org/  (baixe a versão LTS)"
  echo "  Após instalar, rode este script novamente."
  exit 1
fi
ok "Node.js encontrado: $(node --version)"

# ── 3. Instala dependências Python ───────────────────────────
echo "[ 3/5 ] Instalando dependências Python..."
$PYTHON -m pip install --quiet --upgrade pip
$PYTHON -m pip install --quiet python-dotenv notion-client
ok "Dependências Python instaladas."

# ── 4. Instala dependências Node ─────────────────────────────
echo "[ 4/5 ] Instalando dependências Node.js..."
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"
npm install --silent docx
ok "Dependência 'docx' instalada."

# ── 5. Configura o agendamento (launchd) ─────────────────────
echo "[ 5/5 ] Configurando agendamento às 7h no macOS..."

PLIST_NAME="br.adv.fernandeserego.relatorio-diario"
PLIST_PATH="$HOME/Library/LaunchAgents/${PLIST_NAME}.plist"
PYTHON_PATH="$(which $PYTHON)"
LOG_DIR="$HOME/Library/Logs/RelatorioFR"
mkdir -p "$LOG_DIR"

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
        <string>${PYTHON_PATH}</string>
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
        <string>/usr/local/bin:/usr/bin:/bin:/opt/homebrew/bin</string>
    </dict>
</dict>
</plist>
PLIST

# Carrega o agendamento
launchctl unload "$PLIST_PATH" 2>/dev/null || true
launchctl load -w "$PLIST_PATH"
ok "Agendamento configurado: todo dia às 7h00."

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
echo "  Para testar agora, execute:"
echo "  cd '$SCRIPT_DIR' && $PYTHON relatorio_diario.py"
echo ""
