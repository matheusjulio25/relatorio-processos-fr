#!/usr/bin/env python3
"""Entre os PDFs baixados, identifica QUAL e o laudo do perito judicial e isola a conclusao.
Usa o nome do perito da aba de pericias como ancora."""
import json, re, subprocess, glob, collections, unicodedata
from pathlib import Path
def sem(s): return ''.join(c for c in unicodedata.normalize('NFD',s or '') if unicodedata.category(c)!='Mn').lower()
def txt(p):
    try: return subprocess.run(['pdftotext','-layout',p,'-'],capture_output=True,text=True,timeout=90).stdout or ''
    except Exception: return ''
PER=json.load(open('mapas/aba_pericia.json',encoding='utf-8'))
# sinais de que o PDF é o LAUDO DO PERITO (e nao PA do INSS, peca nossa, diploma)
EH=[(r'quesito',3),(r'periciad',3),(r'anamnese',4),(r'exame\s+f[íi]sico',4),
    (r'perito\s+judicial|perita\s+judicial',5),(r'CRM[/\s]',2),(r'CRESS',2),
    (r'IF-?Br',3),(r'impedimento\s+de\s+longo\s+prazo',2),(r'CID',1),
    (r'Resposta\s*:',3),(r'R\s*-\s*[A-ZÀ-Ú]',2),(r'\(\s*[Xx]\s*\)',3),
    (r'CONCLUS[ÃA]O\s*:',5),(r'DII|DID',2),(r'assino\s+o\s+presente|declaro',2)]
NAO=[(r'Meu\s+INSS|meu\.inss|gov\.br/meuinss',6),(r'Assinatura\s+Digital\s+Institucional',5),
     (r'ANEXO\s+III|INSTRUMENTO\s+UNIFICADO\s+DE\s+AVALIA',25),   # formulario em branco da Portaria
     (r'Observa[çc][õo]es\s+do\s+avaliador\(a\)\s*:\s*Profissional',20),
     (r'Portaria\s+Conjunta|Instru[çc][ãa]o\s+Normativa\s+INSS',10),
     (r'OF[ÍI]CIO\s+REQUISIT[ÓO]RIO|Solicita[çc][ãa]o\s+de\s+Pagamento',20),
     (r'AJG\s*-\s*Sistema',20),(r'MANDADO\s+DE\s+VERIFICA[ÇC][ÃA]O',8),
     (r'OAB/PE',6),(r'Pede\s+deferimento',6),(r'CONCLUS[ÃA]O\s+DE\s+CURSO',8),
     (r'CARGA\s+HOR[ÁA]RIA',8),(r'EXTRATO\s+PREVIDENCI',6),(r'Procurador\s+Federal',6),
     (r'CNIS|Vínculo\s+trabalhista',5),(r'CadÚnico|Cad[Uu]nico',3)]
out={}
files=collections.defaultdict(list)
for f in sorted(glob.glob('mapas/laudos_pdf2/*.pdf')):
    c=Path(f).stem.split('__')[0].replace('_','.')
    c=re.sub(r'^(\d{7})\.(\d{2})\.(\d{4})\.(\d)\.(\d{2})\.(\d{4})$',r'\1-\2.\3.\4.\5.\6',c)
    files[c].append(f)
for cnj,fs in sorted(files.items()):
    peritos=[sem(p.get('perito','').split('-')[0].strip()) for p in PER.get(cnj,{}).get('pericias',[])]
    peritos=[p for p in peritos if len(p)>8]
    cands=[]
    for f in fs:
        t=txt(f)
        if len(t.strip())<400: continue
        ts=sem(t); sc=0
        for rx,w in EH: sc += w*min(len(re.findall(rx,t,re.I)),3)
        for rx,w in NAO: sc -= w*min(len(re.findall(rx,t,re.I)),3)
        if any(p in ts for p in peritos): sc += 20      # ancora: nome do perito
        cands.append((sc,f,len(t)))
    cands.sort(reverse=True)
    out[cnj]={'cands':[{'score':s,'pdf':f,'chars':n} for s,f,n in cands[:4]],
              'peritos':peritos,'melhor':cands[0][1] if cands and cands[0][0]>0 else None}
json.dump(out,open('mapas/laudo_certo.json','w',encoding='utf-8'),ensure_ascii=False,indent=1)
ok=sum(1 for v in out.values() if v['melhor'])
print(f'processos: {len(out)} | com laudo identificado: {ok} | sem: {len(out)-ok}')
