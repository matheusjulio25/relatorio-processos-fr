#!/usr/bin/env python3
"""Le os PDFs baixados do laudo (pdftotext) e isola a CONCLUSAO pericial de cada processo.
Saida: mapas/laudo_conclusao.json  + /tmp/conclusoes_pdf.txt para leitura."""
import json, re, subprocess, glob, collections
from pathlib import Path

def txt(p):
    try:
        return subprocess.run(['pdftotext','-layout',p,'-'],capture_output=True,
                              text=True,timeout=90).stdout or ''
    except Exception:
        return ''

# marcadores de que o PDF É o laudo (e nao o diploma/anexo do CNIS)
EH_LAUDO=re.compile(r'quesito|periciad|anamnese|exame\s+f[íi]sico|CID|impedimento|'
                    r'incapacidade|estudo\s+social|IF-?Br|assistente\s+social',re.I)
RUIDO=re.compile(r'(conclus[ãa]o\s+do\s+curso|carga\s+hor[áa]ria|m[ée]dia\s+final|'
                 r'confere\s+o\s+t[íi]tulo|diploma|extrato\s+previdenci)',re.I)
CONC=re.compile(r'(CONCLUS[ÃAO]\w*\s*:?[\s\S]{0,900}'
  r'|(?:n[ãa]o\s+)?h[áa]\s+incapacidade[^\n]{0,200}'
  r'|impedimento[s]?\s+de\s+longo\s+prazo[^\n]{0,220}'
  r'|(?:n[ãa]o\s+)?preenche[^\n]{0,200}'
  r'|n[ãa]o\s+se\s+enquadra[^\n]{0,180}'
  r'|RESULTADO\s*:[^\n]{0,150}'
  r'|n[íi]vel\s+de\s+suporte\s*\d[^\n]{0,180})',re.I)

PDFS=collections.defaultdict(list)
for f in sorted(glob.glob('mapas/laudos_pdf/*.pdf')):
    cnj=Path(f).stem.split('__')[0].replace('_','.')
    cnj=re.sub(r'^(\d{7})\.(\d{2})\.(\d{4})\.(\d)\.(\d{2})\.(\d{4})$',r'\1-\2.\3.\4.\5.\6',cnj)
    PDFS[cnj].append(f)

out={}
linhas=[]
for cnj,fs in sorted(PDFS.items()):
    melhor=None
    for f in fs:
        t=txt(f)
        if len(t.strip())<300: continue
        if RUIDO.search(t[:1500]) and not EH_LAUDO.search(t[:3000]): continue
        score=len(EH_LAUDO.findall(t))
        if melhor is None or score>melhor[0]: melhor=(score,f,t)
    if not melhor:
        out[cnj]={'ok':False,'motivo':'nenhum PDF com texto de laudo'}; continue
    score,f,t=melhor
    tt=re.sub(r'[ \t]+',' ',t)
    trechos=[]
    for m in CONC.finditer(tt):
        g=re.sub(r'\s+',' ',m.group(0)).strip()
        if len(g)<50 or RUIDO.search(g): continue
        if any(abs(m.start()-s)<600 for s in [x[0] for x in trechos]): continue
        trechos.append((m.start(),g[:700]))
        if len(trechos)>=3: break
    out[cnj]={'ok':True,'pdf':f,'score':score,'chars':len(t),
              'trechos':[g for _,g in trechos]}
    linhas.append(f"\n### {cnj}  [{Path(f).name}]")
    for g in [g for _,g in trechos]: linhas.append('  * '+g)
    if not trechos: linhas.append('  * [sem trecho] '+re.sub(r'\s+',' ',tt)[-400:])
json.dump(out,open('mapas/laudo_conclusao.json','w',encoding='utf-8'),ensure_ascii=False,indent=1)
Path('/tmp/conclusoes_pdf.txt').write_text('\n'.join(linhas),encoding='utf-8')
print('processos com PDF:',len(PDFS),'| com laudo legivel:',sum(1 for v in out.values() if v['ok']))
