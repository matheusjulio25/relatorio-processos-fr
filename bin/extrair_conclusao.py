#!/usr/bin/env python3
"""Isola o trecho decisorio de cada laudo (conclusao / quesitos de incapacidade)."""
import json, re, sys
L = json.load(open('mapas/laudos_texto.json', encoding='utf-8'))
M = {r['cnj']: r for r in json.load(open('mapas/maturidade_0309.json', encoding='utf-8'))}
PAT = [r'CONCLUS(?:Ã|A)O', r'CONCLUS(?:Õ|O)ES',
       r'impedimento[s]?\s+de\s+longo\s+prazo',
       r'h[áa]\s+incapacidade', r'n[ãa]o\s+h[áa]\s+incapacidade',
       r'incapacidade\s+(?:total|parcial|atual|laboral)',
       r'\bé\s+(?:portador|pessoa\s+com\s+defici)']
RX = re.compile('|'.join(PAT), re.I)
alvo = sys.argv[1:] if len(sys.argv) > 1 else sorted(L)
for cnj in alvo:
    v = L.get(cnj, {})
    if not v.get('ok'): continue
    lau = [l for l in v.get('laudos', []) if l['chars'] > 1500]
    if not lau: continue
    m = M.get(cnj, {})
    print('=' * 100)
    print(f"{cnj} | {m.get('cliente','?')} | laudo_med={m.get('laudo_medico_em','-')} "
          f"soc={m.get('laudo_social_em','-')} | T187={m.get('dispensa_social_tema187')} "
          f"| concl={m.get('conclusos_em') or '-'} | antes={m.get('resultado_laudo')}")
    for l in lau:
        t = re.sub(r'\s+', ' ', open(l['path'], encoding='utf-8').read())
        hits = [mm.start() for mm in RX.finditer(t)]
        print(f"  -- {l['tipo']} ({l['chars']}ch) --")
        if not hits:
            print('   ', t[:600]); continue
        seen = []
        for h in hits:
            if any(abs(h - s) < 500 for s in seen): continue
            seen.append(h)
            print('   ...', t[max(0, h - 150):h + 700].strip())
            if len(seen) >= 3: break
