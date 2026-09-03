#!/usr/bin/env python3
"""Classifica o laudo (PDF real) em favoravel/desfavoravel por marcadores decisivos."""
import json, re, subprocess, collections
C=json.load(open('mapas/laudo_conclusao.json',encoding='utf-8'))
def txt(p):
    return subprocess.run(['pdftotext','-layout',p,'-'],capture_output=True,text=True,timeout=90).stdout or ''
# regras do formulario que NAO sao resposta
RUIDO=[r'se\s+resposta\s+da\s+8\s+for\s+N[ÃA]O', r'independentemente\s+da\s+soma',
       r'Se\s+maior\s+ou\s+igual\s+a\s+\d+[^\n]{0,70}defici[êe]ncia',
       r'Se\s+menor\s+que\s+\d+[^\n]{0,50}defici[êe]ncia',
       r'—\s*n[ãa]o\s+é\s+Pessoa\s+com\s+Defici[êe]ncia\s*[–-]',
       r'\(\s*\)\s*(?:Sim|N[ãa]o)']          # alternativa NAO marcada
FAV=[(r'\bh[áa]\s+incapacidade',4),(r'incapacidade\s+total\s+e\s+permanente',5),
 (r'incapacidade\s+(?:atual\s+)?total',3),(r'\bincapaz\b',2),
 (r'possui\s+impedimento\s+de\s+longo\s+prazo',5),
 (r'h[áa]\s+impedimento\s+de\s+longo\s+prazo',5),
 (r'preenche\s+os\s+crit[ée]rios\s+de\s+pessoa\s+com\s+defici',6),
 (r'defici[êe]ncia\s+(?:grave|moderada)\b',4),
 (r'\bé\s+pessoa\s+com\s+defici[êe]ncia',5),
 (r'n[íi]vel\s+de\s+suporte\s*[23]',3),
 (r'\(\s*[Xx]\s*\)\s*Sim[^\n]{0,60}impedimento',5),
 (r'apresentando\s+defici[êe]ncia\s+(?:de|intelectual|sensorial)',4),
 (r'impedimento[^\n]{0,60}(?:obstruir|obstru[ií])[^\n]{0,60}participa',4)]
DES=[(r'n[ãa]o\s+h[áa]\s+incapacidade',5),(r'N[ÃA]O\s+EXISTE\s+INCAPACIDADE',6),
 (r'n[ãa]o\s+possui\s+impedimento\s+de\s+longo\s+prazo',6),
 (r'n[ãa]o\s+(?:é|e)\s+pessoa\s+com\s+defici[êe]ncia',6),
 (r'n[ãa]o\s+se\s+enquadra\s+como\s+pessoa\s+com\s+defici',6),
 (r'n[ãa]o\s+preench\w+[^\n]{0,60}(?:crit[ée]rio|requisito)[^\n]{0,60}defici',6),
 (r'apresenta[nd]*o?\s*-?\s*se\s+sem\s+defici[êe]ncia',6),
 (r'sem\s+impedimento\s+de\s+longo\s+prazo',5),
 (r'capacidade\s+(?:laboral\s+)?preservada',4),
 (r'Fun[çc][õo]es\s+Mentais\s*:\s*nenhuma',3),
 (r'\bapt[oa]\s+(?:para|ao)\s+(?:o\s+)?trabalho',3),
 (r'mera\s+supervis[ãa]o',2)]
RXR=re.compile('|'.join(RUIDO),re.I)
out={}
for cnj,v in C.items():
    if not v.get('ok'): out[cnj]={'v':'sem_texto'}; continue
    t=RXR.sub(' ',txt(v['pdf']))
    f=d=0; ev=[]
    for rx,w in FAV:
        n=len(re.findall(rx,t,re.I))
        if n: f+=w*min(n,2); ev.append(f'+{w}x{n} {rx[:32]}')
    for rx,w in DES:
        n=len(re.findall(rx,t,re.I))
        if n: d+=w*min(n,2); ev.append(f'-{w}x{n} {rx[:32]}')
    ver=('ambiguo' if f and d and abs(f-d)<5 else 'favoravel' if f>d else
         'desfavoravel' if d>f else 'ambiguo')
    out[cnj]={'v':ver,'f':f,'d':d,'ev':ev,'pdf':v['pdf']}
json.dump(out,open('mapas/laudo_pdf_veredito.json','w',encoding='utf-8'),ensure_ascii=False,indent=1)
print(collections.Counter(v['v'] for v in out.values()).most_common())
