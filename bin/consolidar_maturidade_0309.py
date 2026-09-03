#!/usr/bin/env python3
"""Consolida a rodada 03/09/2026: verificacao PJe (423 vivos) x classificacao 10/07
   -> mapas/maturidade_0309.json  (um registro por processo, taxonomia da skill)."""
import json, re, collections
from datetime import datetime
from pathlib import Path

CORTE = datetime(2026, 7, 10)
HOJE  = datetime(2026, 9, 3)
def dig(c): return re.sub(r'\D', '', c or '')
def d2(s):
    try: return datetime.strptime(s, '%d/%m/%Y')
    except Exception: return None

AC = json.load(open('mapas/acervo_atual.json', encoding='utf-8'))
acv = {dig(p['cnj']): p for p in AC['processos']}
OLD = {dig(a['cnj']): a for a in json.load(open('mapas/analise_cnj_full.json', encoding='utf-8'))}

VER = {}
for suf in ('', '_a', '_b'):
    f = Path(f'mapas/verificacao_pje{suf}.json')
    if f.exists():
        for k, v in json.loads(f.read_text(encoding='utf-8')).items():
            if v.get('ok'):
                VER.setdefault(dig(k), (suf, v))
                if suf in ('_a', '_b'):        # rodada nova tem precedencia
                    VER[dig(k)] = (suf, v)

def estado(s):
    if s.get('arquivado') or s.get('transito'): return 'arquivado_extinto'
    if s.get('cumprimento') or s.get('rpv'):    return 'cumprimento_sentenca'
    if s.get('turma_recursal') or s.get('recurso'): return 'em_recurso'
    if s.get('sentenca'):                        return 'sentenciado'
    return 'ativo_sem_sentenca'

out = []
for c, (suf, v) in VER.items():
    s = v.get('sinais', {})
    old = OLD.get(c, {})
    p = acv.get(c, {})
    lp, ls = d2(s.get('laudo_pericial', '')), d2(s.get('laudo_social', ''))
    ml, cn = d2(s.get('manif_laudo', '')), d2(s.get('conclusos', ''))
    est = estado(s)
    r = dict(
        cnj=p.get('cnj') or old.get('cnj') or c,
        cliente=(p.get('partes') or '').split(' X ')[0].strip()[:38],
        vara=p.get('vara', ''),
        rodada='03/09/2026' if suf in ('_a', '_b') else '17/08/2026',
        estado_processo=est,
        estado_antes=old.get('estado_processo', 'nunca_classificado'),
        classe_beneficio=old.get('classe_beneficio', 'indefinido'),
        motivo_indeferimento=old.get('motivo_indeferimento', 'nao_identificado'),
        dispensa_social_tema187=old.get('dispensa_social_tema187'),
        resultado_laudo=old.get('resultado_laudo', 'nao_verificado'),
        laudo_medico_em=s.get('laudo_pericial', ''),
        laudo_social_em=s.get('laudo_social', ''),
        manif_laudo_em=s.get('manif_laudo', ''),
        conclusos_em=s.get('conclusos', ''),
        ultima_data=v.get('ultima_data', ''),
        n_novos=v.get('n_novos', 0),
        pericia_medica='realizada' if lp else old.get('pericia_medica', 'nao_ha'),
        pericia_social='realizada' if ls else old.get('pericia_social', 'nao_ha'),
        # NOVIDADES desde 10/07
        laudo_medico_novo=bool(lp and lp > CORTE),
        laudo_social_novo=bool(ls and ls > CORTE),
        conclusos_novo=bool(cn and cn > CORTE),
        # laudo juntado e ainda SEM manifestacao do escritorio
        laudo_sem_manifestacao=bool(lp and (not ml or ml < lp)),
        novo_no_acervo=(c not in OLD),
    )
    out.append(r)

json.dump(out, open('mapas/maturidade_0309.json', 'w', encoding='utf-8'),
          ensure_ascii=False, indent=1)
print(f'{len(out)} processos consolidados -> mapas/maturidade_0309.json')
print('estado:', collections.Counter(r['estado_processo'] for r in out).most_common())
