#!/bin/bash
# Roda pelo launchd diariamente. Gera o relatorio e copia pra Desktop.
set -e

REPO="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO"
source "$REPO/.venv/bin/activate"

# Garante que o painel abra rapido (TOTP automatico se .env tiver PJE_TOTP_SECRET).
# Roda headless por padrao; se quiser ver o Chrome, troca pra --no-headless.
python -m coletor_pje.cli relatorio

HOJE="$(date +%Y-%m-%d)"
SRC="$REPO/relatorios/relatorio-$HOJE.md"
DST="$HOME/Desktop/relatorio-pje-$HOJE.md"

if [ -f "$SRC" ]; then
    cp "$SRC" "$DST"
    echo "relatorio copiado para $DST"
    # notificacao no macOS
    osascript -e "display notification \"Relatorio pronto em $DST\" with title \"PJe TRF5\"" 2>/dev/null || true
else
    echo "AVISO: $SRC nao encontrado"
fi
