#!/usr/bin/env python3
"""Filas de acao da rodada 03/09/2026."""
import json, re, collections
from datetime import datetime
M=[r for r in json.load(open('mapas/maturidade_0309.json',encoding='utf-8')) if r['rodada']=='03/09/2026']
V=json.load(open('mapas/laudo_veredito.json',encoding='utf-8'))
HOJE=datetime(2026,9,3)
def d2(s):
    try: return datetime.strptime(s,'%d/%m/%Y')
    except: return None
MAP={'favoravel':'favoravel','desfavoravel':'desfavoravel','ambiguo':'nao_verificado',
     'sem_texto':'nao_verificado','social_favoravel':'nao_verificado'}
for r in M:
    v=V.get(r['cnj'])
    r['laudo_lido_0309']=v['veredito'] if v else None
    if v and MAP[v['veredito']]!='nao_verificado':
        r['resultado_laudo']=MAP[v['veredito']]; r['laudo_fonte']='lido 03/09'
    else:
        r['laudo_fonte']='10/07' if r['resultado_laudo'] not in ('nao_verificado',) else 'nao lido'
    r['_c']=d2(r['conclusos_em']); r['_lm']=d2(r['laudo_medico_em']); r['_ml']=d2(r['manif_laudo_em'])
at=[r for r in M if r['estado_processo']=='ativo_sem_sentenca']
F={}
F['1b_URGENTE_conclusos_laudo_adverso']=[r for r in at if r['_c'] and r['resultado_laudo']=='desfavoravel']
F['1_DESPACHAR_laudo_favoravel']=[r for r in at if r['resultado_laudo']=='favoravel']
F['1c_TEMA187']=[r for r in at if r['dispensa_social_tema187'] and r['pericia_social']!='realizada']
F['A_laudo_novo_sem_manifestacao']=[r for r in at if (r['laudo_medico_novo'] or r['laudo_social_novo']) and r['laudo_sem_manifestacao']]
F['2_laudo_nao_lido']=[r for r in at if r['laudo_medico_em'] and r['resultado_laudo']=='nao_verificado']
F['3_aguardando_pericia']=[r for r in at if not r['laudo_medico_em'] and not r['laudo_social_em']]
F['4_em_recurso']=[r for r in M if r['estado_processo']=='em_recurso']
F['5_cumprimento']=[r for r in M if r['estado_processo']=='cumprimento_sentenca']
F['6_sentenciado']=[r for r in M if r['estado_processo']=='sentenciado']
F['7_arquivado']=[r for r in M if r['estado_processo']=='arquivado_extinto']
for k,v in F.items(): print(f'{k:38s} {len(v):4d}')
json.dump({k:[r['cnj'] for r in v] for k,v in F.items()},
          open('mapas/filas_0309.json','w',encoding='utf-8'),ensure_ascii=False,indent=1)
for r in M: r.pop('_c',None); r.pop('_lm',None); r.pop('_ml',None)
json.dump(M,open('mapas/maturidade_0309_final.json','w',encoding='utf-8'),ensure_ascii=False,indent=1)
print('\n-> mapas/filas_0309.json + mapas/maturidade_0309_final.json')
