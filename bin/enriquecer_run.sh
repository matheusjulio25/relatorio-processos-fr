#!/bin/zsh
# Enriquecimento por CNJ (fase 2a) até concluir, retomando sozinho.
cd /Users/matheusjuliorego/relatorio-processos-fr || exit 1
TOTAL=$(python3 -c "import json;print(len(json.load(open('mapas/pericias_por_processo.json'))))")
prev=-1; stall=0
for i in {1..60}; do
  echo "[wrap-enr] === rodada $i ($prev/$TOTAL) ==="
  PYTHONUNBUFFERED=1 .venv/bin/python bin/enriquecer_cnj.py 2>&1
  done=$(python3 -c "import json,os;print(len(json.load(open('mapas/enriquecimento_cnj.json'))) if os.path.exists('mapas/enriquecimento_cnj.json') else 0)" 2>/dev/null || echo 0)
  echo "[wrap-enr] rodada $i: $done/$TOTAL"
  if [ "$done" -ge "$TOTAL" ]; then echo "[wrap-enr] COMPLETO ($done/$TOTAL)"; break; fi
  if [ "$done" -le "$prev" ]; then stall=$((stall+1)); else stall=0; fi
  prev=$done
  if [ "$stall" -ge 3 ]; then echo "[wrap-enr] sem progresso — parando em $done/$TOTAL"; break; fi
  sleep 4
done
echo "[wrap-enr] gerando planilha final..."
python3 bin/planilha_maturidade.py 2>&1 | tail -2
echo "[wrap-enr] FIM DO WRAPPER"
