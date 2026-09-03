#!/usr/bin/env python3
"""KPI Possibilidade de Exito — rodada 03/09/2026.
Base do painel = universo da triagem (288 de 10/07 U 423 vivos lidos em 03/09).
Desfechos: COMPILADO_sentencas.json (533) + classificacao 10/07. MS de mora fora."""
import json, re, collections
def dig(c): return re.sub(r'\D','',c or '')

M   = [r for r in json.load(open('mapas/maturidade_0309_final.json',encoding='utf-8')) if r['rodada']=='03/09/2026']
OLD = json.load(open('mapas/analise_cnj_full.json',encoding='utf-8'))
SENT= json.load(open('mapas/COMPILADO_sentencas.json',encoding='utf-8'))
VER = json.load(open('mapas/laudo_veredito.json',encoding='utf-8'))
ACV = {dig(p['cnj']):p for p in json.load(open('mapas/acervo_atual.json',encoding='utf-8'))['processos']}
FIL = json.load(open('mapas/filas_0309.json',encoding='utf-8'))
LIDOP={k for k in json.load(open('mapas/providencias_conclusos.json',encoding='utf-8')) if not k.startswith('_')}

old={dig(a['cnj']):a for a in OLD}; viv={dig(r['cnj']):r for r in M}
sen={}
for x in SENT:
    if x.get('res') not in ('indefinido','pendente_verificacao') and x.get('bloco')!='ms':
        sen[dig(x['cnj'])]=x

def tipo_ext(x):
    d=(x.get('disp') or '').lower()
    if any(k in d for k in ('indefiro a petição inicial','indefiro a inicial','485, i','art. 321','330, iv')):
        return 'pre_instrucao'
    if any(k in d for k in ('abandono','485, iii','art. 51','não compare','ausência')): return 'abandono'
    if 'desist' in d or '485, viii' in d: return 'desistencia'
    return 'outros'

BEN={'bpc_deficiencia':'BPC deficiência','bpc_idoso':'BPC idoso','incapacidade':'Incapacidade',
     'pensao_morte':'Pensão por morte','outro':'Outro','indefinido':'Indefinido'}
EST={'ativo_sem_sentenca':'Ativo','sentenciado':'Sentenciado','arquivado_extinto':'Arquivado',
     'em_recurso':'Em recurso','cumprimento_sentenca':'Cumprimento'}
DESF={'procedente':'Procedente','parcialmente_procedente':'Parcial','homologacao':'Acordo homologado',
      'improcedente':'Improcedente','extincao_sem_merito':'Extinto sem mérito'}
EXITO={'procedente','parcialmente_procedente','homologacao'}
# providencia curta por processo (mesma regra da planilha)
def provid(cnj,r):
    S={k:set(v) for k,v in FIL.items()}
    return None


# ---- providencia por processo ativo (mesma regra da planilha de providencias) ----
SF={k:set(v) for k,v in FIL.items()}
CURTA=json.load(open('mapas/providencias_curtas.json',encoding='utf-8'))

def provid_de(cnj,v):
    """(ordem, prioridade, providencia, motivo, prazo) para os ATIVOS."""
    if not v:
        return dict(o=8,pri='Conferir',p='Confirmar se ainda está ativo',
                    mo='Constava ativo em 10/07 e não apareceu no acervo de 03/09',pz='48h')
    if v['estado_processo']!='ativo_sem_sentenca':
        return dict(o=0,pri='',p='',mo='',pz='')
    t187=v.get('dispensa_social_tema187')
    if cnj in CURTA:
        pp,mot=CURTA[cnj]
        if pp.startswith('Impugnar'): return dict(o=1,pri='Urgente',p=pp,mo=mot,pz='48h')
        if pp.startswith('Requerer'): return dict(o=2,pri='Despachar',p=pp,mo=mot,pz='5 dias')
        if pp.startswith('Ler') or pp.startswith('Conferir'): return dict(o=3,pri='Ler laudo',p=pp,mo=mot,pz='48h')
        return dict(o=4,pri='Manifestar',p=pp,mo=mot,pz='72h')
    if cnj in SF['1b_URGENTE_conclusos_laudo_adverso']:
        return dict(o=1,pri='Urgente',p='Impugnar o laudo',
                    mo=f"Conclusos desde {v['conclusos_em']} com laudo desfavorável",pz='48h')
    if cnj in SF['A_laudo_novo_sem_manifestacao']:
        dt=v['laudo_medico_em'] or v['laudo_social_em']; res=v['resultado_laudo']
        if res=='desfavoravel': return dict(o=4,pri='Manifestar',p='Impugnar o laudo',mo=f'Laudo desfavorável de {dt}, sem manifestação',pz='72h')
        if res=='favoravel':    return dict(o=4,pri='Manifestar',p='Manifestar e requerer julgamento',mo=f'Laudo favorável de {dt}, sem manifestação',pz='72h')
        return dict(o=4,pri='Manifestar',p='Manifestar sobre o laudo',mo=f'Laudo de {dt} sem manifestação nossa',pz='72h')
    if cnj in SF['1_DESPACHAR_laudo_favoravel']:
        mo='Laudo favorável; instrução encerrada'
        if t187: return dict(o=2,pri='Despachar',p='Requerer julgamento + Tema 187',mo=mo+'; social dispensável',pz='5 dias')
        if v['pericia_social']=='designada_pendente':
            return dict(o=2,pri='Despachar',p='Requerer julgamento; social pendente',mo=mo,pz='5 dias')
        return dict(o=2,pri='Despachar',p='Requerer julgamento',mo=mo,pz='5 dias')
    if cnj in SF['1c_TEMA187']:
        return dict(o=5,pri='Tema 187',p='Requerer dispensa da social + julgamento',
                    mo='Indeferimento por deficiência; renda incontroversa',pz='72h')
    if cnj in SF['2_laudo_nao_lido']:
        return dict(o=3,pri='Ler laudo',p='Ler o laudo e decidir',
                    mo=f"Laudo de {v['laudo_medico_em'] or v['laudo_social_em']}; resultado não apurado",pz='5 dias')
    if cnj in SF['3_aguardando_pericia']:
        return dict(o=6,pri='Perícia',p='Cobrar designação + antifalta D-3/D-1',
                    mo='Ativo, sem laudo nos autos',pz='contínuo')
    return dict(o=7,pri='Acompanhar',p='Acompanhar',mo='Ativo, sem providência específica mapeada',pz='—')

rows=[]
for c in set(viv)|set(old):
    v=viv.get(c); o=old.get(c,{}); s=sen.get(c); a=ACV.get(c,{})
    cnj=(v or o).get('cnj') or (s or {}).get('cnj') or c
    lv=VER.get(cnj)
    laudo=(v or o).get('resultado_laudo','nao_verificado')
    if lv and lv['veredito'] in ('favoravel','desfavoravel'): laudo=lv['veredito']
    t187=(v or o).get('dispensa_social_tema187')
    estado = v['estado_processo'] if v else ('arquivado_extinto' if s else o.get('estado_processo','arquivado_extinto'))
    res = s['res'] if s else (o.get('resultado_sentenca') if not v else None)
    if res in ('sem_sentenca','nao_verificado'): res=None
    if laudo=='favoravel':            f='A1' if t187 else 'A2'
    elif laudo=='desfavoravel':       f='B'
    elif laudo=='sem_laudo_judicial': f='C'
    else:                             f='D'
    if v and not v['laudo_medico_em'] and not v['laudo_social_em'] and f=='D': f='C'
    rows.append(dict(
        c=cnj, n=(v['cliente'] if v else (s.get('autor') if s else '')) or '',
        b=BEN.get((v or o).get('classe_beneficio','indefinido'),'Indefinido'),
        e=EST.get(estado,'Arquivado'), f=f, t=1 if t187 else 0,
        d=DESF.get(res,'') if res else '',
        x=(True if res in EXITO else False if res=='improcedente' else None),
        te=(tipo_ext(s) if s and s['res']=='extincao_sem_merito' else ''),
        v=1 if v else 0, li=1 if cnj in LIDOP else 0,
        **(provid_de(cnj,v) if estado=='ativo_sem_sentenca' else dict(o=0,pri='',p='',mo='',pz='')),
        vara=(v['vara'] if v else (s or {}).get('vara','')) or '',
        nv=1 if (v and v['novo_no_acervo']) else 0,
    ))

cal={}
for f in ('A1','A2','C','B','D'):
    dd=[r for r in rows if r['f']==f and r['x'] is not None]
    if dd: cal[f]=dict(n=len(dd),ex=sum(1 for r in dd if r['x']),
                       pem=round(100*sum(1 for r in dd if r['x'])/len(dd),1))
dec=[r for r in rows if r['x'] is not None]
enc=[r for r in rows if r['d']]
ext=[r for r in enc if r['d']=='Extinto sem mérito']
ativos=[r for r in rows if r['e']=='Ativo']
allm=[x for x in SENT if x.get('bloco')!='ms' and x.get('res') not in ('indefinido','pendente_verificacao')]
alle=[x for x in allm if x['res']=='extincao_sem_merito']
pre_all=sum(1 for x in alle if tipo_ext(x)=='pre_instrucao')

K=dict(
 base=len(rows), vivos=len(viv), acervo=len(ACV), ativos=len(ativos),
 decididos=len(dec), exitos=sum(1 for r in dec if r['x']),
 pem=round(100*sum(1 for r in dec if r['x'])/len(dec),1),
 encerrados=len(enc), extintos=len(ext),
 resm=round(100*len(ext)/len(enc),1),
 ext_tipo=dict(collections.Counter(r['te'] for r in ext)),
 cal=cal,
 ativos_faixa=dict(collections.Counter(r['f'] for r in ativos)),
 t187_total=sum(1 for r in rows if r['t']), t187_ativos=sum(1 for r in ativos if r['t']),
 t187_A1=sum(1 for r in ativos if r['t'] and r['f']=='A1'),
 sent_total=len(allm), sent_ext=len(alle), pre_instrucao=pre_all,
 pre_pct=round(100*pre_all/len(allm),1),
 laudos_lidos=len(LIDOP),
 filas={k:len(v) for k,v in FIL.items()},
)
json.dump({'rows':rows,'k':K},open('mapas/kpi_0309.json','w',encoding='utf-8'),ensure_ascii=False)
print(json.dumps(K,ensure_ascii=False,indent=1))
esp=sum(round(K['cal'][f]['pem']/100*n,1) for f,n in K['ativos_faixa'].items() if f in K['cal'] and f in ('A1','A2','B'))
print('\nprojetaveis (A1+A2+B):',sum(n for f,n in K['ativos_faixa'].items() if f in ('A1','A2','B')),'| exitos esperados ~',round(esp))
