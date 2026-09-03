#!/usr/bin/env python3
"""Providencias — classificacao binaria: laudo favoravel = DESPACHAR, desfavoravel = IMPUGNAR."""
import json, collections
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment
from openpyxl.utils import get_column_letter
BRAND="7F8187"; SUB="5F6066"; VERM="C0392B"; VERDE="1E7E34"; CINZA="777777"

M={r['cnj']:r for r in json.load(open('mapas/maturidade_0309_final.json',encoding='utf-8'))
   if r['rodada']=='03/09/2026'}
K={r['c']:r for r in json.load(open('mapas/kpi_0309.json',encoding='utf-8'))['rows']}
CURTA=json.load(open('mapas/providencias_curtas.json',encoding='utf-8'))
MAPA174=json.load(open('mapas/mapa_174.json',encoding='utf-8'))
MAPA102=json.load(open('mapas/mapa_102.json',encoding='utf-8'))
PER=json.load(open('mapas/aba_pericia.json',encoding='utf-8'))
from datetime import datetime
def _d(x):
    try: return datetime.strptime(x,'%d/%m/%Y')
    except: return None
def pericia_de(cnj):
    """(data, situacao, perito, especialidade) da pericia mais relevante."""
    v=PER.get(cnj)
    if not v or not v.get('ok') or not v['pericias']: return ('','','','')
    ps=v['pericias']
    ORD={'Ausência de Parte':0,'Pendente':1,'Designada':2,'Redesignada':3,
         'Aguardando nomeação no AJG':4,'Cancelada':7,'Realizada':5,'Enviado para pagamento':6}
    ps=sorted(ps,key=lambda p:(ORD.get(p['situacao'],9), -(_d(p['data']).toordinal() if _d(p['data']) else 0)))
    p0=ps[0]
    txt=' '.join(p0.get('cels',[])).lower()
    espec='Social' if ('social' in txt or 'assistent' in txt) else 'Médica'
    return (p0['data'], p0['situacao'], p0.get('perito','')[:40], espec)

def linha(cnj,r):
    """(ordem, acao, providencia, motivo, prazo, cor)"""
    k=K.get(cnj,{}); f=k.get('f','D'); est=r['estado_processo']
    conc=r['conclusos_em']; semman=r['laudo_sem_manifestacao']
    mot=CURTA[cnj][1] if cnj in CURTA else ''

    if est=='ativo_sem_sentenca':
        m2=MAPA102.get(cnj)
        if m2:
            pr,mo2=m2
            if pr.startswith('Impugnar'):  return (1,'Impugnar',pr,mo2,'48h' if conc else '72h',VERM)
            if pr.startswith('ATENÇÃO'):   return (1,'Alerta',pr,mo2,'48h',VERM)
            if pr.startswith('Requerer'):  return (3,'Despachar',pr,mo2,'5 dias',VERDE)
            if pr.startswith('Usar o PA'): return (3,'Despachar',pr,mo2,'5 dias',VERDE)
            if pr.startswith('Manifestar'):return (4,'Manifestar',pr,mo2,'72h',VERDE)
            if pr.startswith('Solicitar'): return (7,'Sem perícia',pr,mo2,'5 dias',CINZA)
            if pr.startswith('Ler'):       return (5,'Ler laudo',pr,mo2,'5 dias',CINZA)
        if f=='B':                                   # laudo desfavoravel
            if not mot: mot=(f'Conclusos desde {conc} com laudo desfavorável' if conc
                             else 'Laudo desfavorável nos autos')
            return (1,'Impugnar','Impugnar o laudo',mot,'48h' if conc else '72h',VERM)
        if f in ('A1','A2'):                         # laudo favoravel
            if not mot: mot=('Laudo favorável, ainda sem manifestação nossa' if semman
                             else 'Laudo favorável; instrução encerrada')
            p='Requerer julgamento'
            if k.get('t')==1: p+=' + Tema 187'
            return (2,'Despachar',p,mot,'5 dias',VERDE)
        m=MAPA174.get(cnj)
        if m:
            pr,mo=m
            if pr=='Impugnar':
                return (1,'Impugnar','Impugnar o laudo',mo,'48h' if conc else '72h',VERM)
            if pr=='Ler o laudo no PJe':
                return (3,'Ler laudo','Ler o laudo no PJe',mo,'5 dias',CINZA)
            if pr.startswith('Justificar'):
                return (2,'Falta à perícia',pr,mo,'48h',VERM)
            if pr.startswith('Cobrar'):
                return (5,'Cobrar laudo',pr,mo,'5 dias',VERM)
            if pr.startswith('Aguardar'):
                return (8,'No prazo',pr,mo,'—',CINZA)
            if pr.startswith('Confirmar'):
                return (6,'Antifalta',pr,mo,'D-3 / D-1',CINZA)
            if pr.startswith('Solicitar'):
                return (7,'Sem perícia',pr,mo,'5 dias',CINZA)
            return (9,'Conferir','Confirmar se ainda está ativo',mo,'48h',CINZA)
        return (7,'Sem perícia','Solicitar designação da perícia',
                'Perícia ainda não produzida','5 dias',CINZA)

    if est=='sentenciado':
        return (5,'Recorrer','Conferir prazo e recorrer se cabível',
                f'Sentença; última mov. {r["ultima_data"]}','48h',VERM)
    if est=='em_recurso':
        return (6,'Turma Recursal','Apresentar memorial','Autos na Turma','conforme pauta',CINZA)
    if est=='cumprimento_sentenca':
        return (7,'Cumprimento','Acompanhar cálculo / RPV','Fase de cumprimento','conforme pauta',CINZA)
    return (8,'—','Nada a fazer','Arquivado / baixa definitiva','—',CINZA)

rows=sorted((linha(c,r)+(c,r['cliente'],r['vara'],r['novo_no_acervo'])) for c,r in M.items())

wb=Workbook(); ws=wb.active; ws.title="Providências"
ws["A1"]="Fernandes & Rêgo Advogados Associados — Providências por processo"
ws["A1"].font=Font(bold=True,size=14,color=BRAND,name="Palatino Linotype")
ws["A2"]="Rodada 03/09/2026 · laudo favorável = despachar · laudo desfavorável = impugnar"
ws["A2"].font=Font(italic=True,size=9,color=SUB,name="Segoe UI")
ws.append([])
COLS=["#","Ação","Processo (CNJ)","Cliente","Providência","Motivo","Prazo","Perícia em","Situação da perícia","Especialidade","Perito","Vara","Novo?"]
ws.append(COLS)
for c in ws[4]:
    c.font=Font(bold=True,color="FFFFFF",name="Segoe UI",size=10)
    c.fill=PatternFill("solid",fgColor=BRAND)
    c.alignment=Alignment(horizontal="center",vertical="center",wrap_text=True)
for i,(o,ac,p,mot,prazo,cor,cnj,cli,vara,novo) in enumerate(rows,1):
    pd_,ps_,pp_,pe_=pericia_de(cnj)
    ws.append([i,ac,cnj,cli,p,mot,prazo,pd_,ps_,pe_ if pd_ else '',pp_,vara,"NOVO" if novo else ""])
    row=ws[ws.max_row]
    for c in row: c.font=Font(name="Segoe UI",size=9)
    row[1].font=Font(name="Segoe UI",size=9,bold=True,color=cor)
    row[2].font=Font(name="Segoe UI",size=9,bold=True)
    row[4].font=Font(name="Segoe UI",size=9,bold=True,color=cor)
    row[6].font=Font(name="Segoe UI",size=9,color=cor)
    if row[8].value in ('Ausência de Parte','Cancelada','Pendente'):
        row[8].font=Font(name="Segoe UI",size=9,bold=True,color=VERM)
    elif row[8].value in ('Enviado para pagamento','Realizada'):
        row[8].font=Font(name="Segoe UI",size=9,bold=True,color=VERDE)
    elif row[8].value: row[8].font=Font(name="Segoe UI",size=9,bold=True,color="B7791F")
for i,w in enumerate([5,16,24,34,40,54,14,13,24,13,34,20,7],1):
    ws.column_dimensions[get_column_letter(i)].width=w
ws.freeze_panes="A5"; ws.auto_filter.ref=f"A4:{get_column_letter(len(COLS))}{ws.max_row}"

rs=wb.create_sheet("Resumo")
rs["A1"]="Providências por ação"
rs["A1"].font=Font(bold=True,size=13,color=BRAND,name="Palatino Linotype")
rs.append([]); rs.append(["Ação","Qtd","Prazo"])
for c in rs[3]:
    c.font=Font(bold=True,color="FFFFFF",name="Segoe UI"); c.fill=PatternFill("solid",fgColor=BRAND)
cnt=collections.Counter((l[0],l[1],l[4]) for l in rows)
for (o,ac,prazo),n in sorted(cnt.items()):
    rs.append([ac,n,prazo])
    for c in rs[rs.max_row]: c.font=Font(name="Segoe UI",size=10)
rs.append([]); rs.append(["TOTAL",len(rows),""])
for c in rs[rs.max_row]: c.font=Font(bold=True,name="Segoe UI")
for i,w in enumerate([22,8,16],1): rs.column_dimensions[get_column_letter(i)].width=w

out="relatorios/Providencias_por_processo_03set2026.xlsx"; wb.save(out)
print("->",out,f"({len(rows)} processos)\n")
for (o,ac,prazo),n in sorted(cnt.items()): print(f"  {ac:16s}{n:5d}  {prazo}")
