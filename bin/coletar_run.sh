#!/bin/zsh
# Coleta de peças (etapa 1) dos 216 prioritários até concluir, retomando sozinho.
cd /Users/matheusjuliorego/relatorio-processos-fr || exit 1
TOTAL=$(python3 -c "import json;d=json.load(open('mapas/pericias_por_processo.json'));print(sum(1 for v in d.values() if v.get('feitas',0)>=1))")
prev=-1; stall=0
for i in {1..80}; do
  echo "[wrap-col] === rodada $i ($prev/$TOTAL) ==="
  PYTHONUNBUFFERED=1 .venv/bin/python bin/coletar_pecas_cnj.py 2>&1 | tee /tmp/coleta_rodada.out
  if grep -q "NAO AUTENTICADO" /tmp/coleta_rodada.out; then echo "[wrap-col] ABORTADO: não autenticado"; break; fi
  done=$(python3 -c "import json,os;print(len(json.load(open('mapas/coleta_cnj.json'))) if os.path.exists('mapas/coleta_cnj.json') else 0)" 2>/dev/null || echo 0)
  echo "[wrap-col] rodada $i: $done/$TOTAL"
  if [ "$done" -ge "$TOTAL" ]; then echo "[wrap-col] COMPLETO ($done/$TOTAL)"; break; fi
  if [ "$done" -le "$prev" ]; then stall=$((stall+1)); else stall=0; fi
  prev=$done
  if [ "$stall" -ge 3 ]; then echo "[wrap-col] sem progresso — parando em $done/$TOTAL"; break; fi
  sleep 4
done
echo "[wrap-col] FIM DO WRAPPER"
