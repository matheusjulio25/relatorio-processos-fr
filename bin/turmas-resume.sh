#!/bin/bash
# Retoma a coleta das Turmas Recursais PE com auto-restart.
# Roda as turmas SEMPRE EM SEQUÊNCIA (t1 -> t3 -> t2). NUNCA em paralelo: são dois
# navegadores e o Mac tem 8 GB — dois browsers simultâneos travam a máquina.
# Relança automaticamente em caso de crash do browser — o checkpoint por página
# (mapas/checkpoint_t_t{N}_*.json) garante que cada relançamento retoma onde parou.
# Para quando o checkpoint da turma some (= turma concluída) OU após 3 execuções
# seguidas SEM progresso (sinal de login/sessão quebrada — evita girar em falso).
# Requer PJE_TOTP_SECRET no .env para re-login automático após expiração da sessão.
set -u

REPO="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO"
LOG_DIR="$REPO/logs"
mkdir -p "$LOG_DIR"

# Execução SEQUENCIAL → todas as turmas usam o MESMO perfil já autenticado (o do t1),
# evitando o relogin falho dos perfis t2/t3. (Não usar com execução paralela.)
export PJE2G_PROFILE_COMPARTILHADO="$REPO/browser-profile-2g-t1"

run_turma() {  # $1 = número da turma (1, 2 ou 3)
  local n="$1"
  local log="$LOG_DIR/turmas_t${n}.log"
  local jsonf="$REPO/mapas/acordaos_tr_t${n}.json"
  local tries=0 empties=0
  while true; do
    tries=$((tries + 1))
    local before; before=$(wc -c < "$jsonf" 2>/dev/null || echo 0)
    echo "[wrapper] === turma $n — tentativa $tries — $(date '+%Y-%m-%d %H:%M:%S') ===" >> "$log"
    PYTHONUNBUFFERED=1 "$REPO/bin/pje" turmas --so-turma "$n" --conc 5 >> "$log" 2>&1
    local code=$?
    # Checkpoint sumiu = turma concluída de verdade.
    if ! ls "$REPO"/mapas/checkpoint_t_t${n}_*.json >/dev/null 2>&1; then
      echo "[wrapper] turma $n CONCLUÍDA (checkpoint removido). exit=$code" >> "$log"
      break
    fi
    # Mede progresso real pelo crescimento do JSON de saída.
    local after; after=$(wc -c < "$jsonf" 2>/dev/null || echo 0)
    if [ "$after" -le "$before" ]; then
      empties=$((empties + 1))
      echo "[wrapper] turma $n: execução SEM progresso ($empties/3) — exit=$code (login/sessão?)" >> "$log"
      if [ "$empties" -ge 3 ]; then
        echo "[wrapper] turma $n ABORTADA: 3 execuções sem progresso. Verifique login/2FA (PJE_TOTP_SECRET)." >> "$log"
        break
      fi
      sleep 20
    else
      empties=0  # houve progresso → reseta o contador de falhas
      echo "[wrapper] turma $n: +$((after - before)) bytes salvos — relançando p/ continuar" >> "$log"
      sleep 5
    fi
  done
}

# Turmas em SEQUÊNCIA (não em paralelo): com --conc 5 cada turma já usa ~728 MB +
# 3 abas; dois browsers simultâneos estouraria os 8 GB. A concorrência interna (CONC)
# dá a vazão; rodar uma turma por vez mantém a memória segura.
echo "[wrapper] iniciando coleta sequencial (t1 → t3 → t2), conc=5 — $(date '+%H:%M:%S')"
run_turma 1
run_turma 3
run_turma 2

echo "[wrapper] FIM — $(date '+%Y-%m-%d %H:%M:%S')"
