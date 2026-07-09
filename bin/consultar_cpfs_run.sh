#!/bin/zsh
# Roda a consulta dos 369 CPFs até concluir, retomando sozinho (resume-safe).
# Cada execução do python pula os CPFs já no checkpoint; se a sessão cair, o
# python sai e este loop relança. Para em: COMPLETO, ou 3 rodadas sem progresso.
cd /Users/matheusjuliorego/relatorio-processos-fr || exit 1

TOTAL=$(.venv/bin/python -c "import re;print(len({re.sub(r'\D','',l) for l in open('mapas/cpfs_consulta.txt') if l.strip()}))")
prev=-1; stall=0

for i in {1..60}; do
  echo "[wrapper] === rodada $i (checkpoint $prev/$TOTAL) ==="
  PYTHONUNBUFFERED=1 .venv/bin/python bin/consultar_cpfs.py 2>&1

  done=$(.venv/bin/python -c "import json,os; print(len(json.load(open('mapas/consulta_cpfs.json'))) if os.path.exists('mapas/consulta_cpfs.json') else 0)" 2>/dev/null || echo 0)
  echo "[wrapper] rodada $i concluída: $done/$TOTAL no checkpoint"

  if [ "$done" -ge "$TOTAL" ]; then echo "[wrapper] COMPLETO ($done/$TOTAL)"; break; fi
  if [ "$done" -le "$prev" ]; then stall=$((stall+1)); else stall=0; fi
  prev=$done
  if [ "$stall" -ge 3 ]; then echo "[wrapper] sem progresso em 3 rodadas — parando em $done/$TOTAL"; break; fi
  sleep 5
done
echo "[wrapper] FIM DO WRAPPER"
