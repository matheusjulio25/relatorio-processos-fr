#!/usr/bin/env python3
"""Pre-classifica o laudo em favoravel/desfavoravel por marcadores FORTES do JEF/PE.
Marca 'ambiguo' quando os sinais conflitam — esses vao para leitura humana."""
import json, re
L = json.load(open('mapas/laudos_texto.json', encoding='utf-8'))

FAV = [
 (r'\bh[áa]\s+incapacidade', 3),
 (r'incapacidade\s+total\s+e\s+(?:permanente|definitiva)', 4),
 (r'incapacidade\s+(?:atual\s+)?total', 3),
 (r'\bincapaz\b(?!\s*\?)', 2),
 (r'possui\s+impedimento\s+de\s+longo\s+prazo', 4),
 (r'defici[êe]ncia\s+(?:grave|moderada)', 4),
 (r'\bé\s+pessoa\s+com\s+defici[êe]ncia', 4),
 (r'impedimento[s]?\s+de\s+longo\s+prazo[^.]{0,80}\bsim\b', 3),
 (r'DII\s+em\s+\d', 2),
 (r'preenche\s+os\s+crit[ée]rios\s+de\s+pessoa\s+com\s+defici', 5),
 (r'n[íi]vel\s+de\s+suporte\s*[23]', 3),
 (r'apresentando\s+defici[êe]ncia', 4),
 (r'impedimento\s+de\s+longo\s+prazo\s+de\s+natureza', 4),
]
DES = [
 (r'n[ãa]o\s+h[áa]\s+incapacidade', 4),
 (r'\bapt[oa]\b\s+(?:para|ao)\s+(?:o\s+)?trabalho', 3),
 (r'n[ãa]o\s+(?:é|e)\s+pessoa\s+com\s+defici[êe]ncia', 4),
 (r'n[ãa]o\s+possui\s+impedimento\s+de\s+longo\s+prazo', 4),
 (r'n[ãa]o\s+se\s+enquadra\s+como\s+pessoa\s+com\s+defici', 4),
 (r'sem\s+impedimento', 3),
 (r'capacidade\s+(?:laboral\s+)?preservada', 3),
 (r'mera\s+supervis[ãa]o', 2),
 (r'defici[êe]ncia\s+leve', 2),
 (r'apresenta[nd]*o?\s*-?\s*se\s+sem\s+defici[êe]ncia', 5),
 (r'n[ãa]o\s+preench(?:ia|e)\s+o\s+crit[ée]rio\s+de\s+defici', 5),
 (r'n[ãa]o\s+preenche\s+os\s+crit[ée]rios\s+de\s+pessoa\s+com\s+defici', 5),
 (r'Funç[õo]es\s+Mentais:\s*nenhuma', 3),
]
# frases de FORMULARIO (texto da regra, nao resposta) — nao pontuam
RUIDO = [r'se\s+resposta\s+da\s+8\s+for\s+N[ÃA]O', r'independentemente\s+da\s+soma',
         r'Se\s+maior\s+ou\s+igual\s+a\s+\d+[^.]{0,60}defici[êe]ncia\s+(?:leve|moderada|grave)',
         r'Se\s+menor\s+que\s+\d+[^.]{0,40}defici[êe]ncia\s+grave',
         r'Se\s+maior\s+ou\s+igual\s+a\s+\d+\s*:\s*n[ãa]o\s+se\s+enquadra',
         r'-\s*n[ãa]o\s+é\s+Pessoa\s+com\s+Defici[êe]ncia\s*[–-]\s*n[ãa]o\s+possui',
         # DIPLOMA/CURRICULO do perito — nao e conteudo do laudo
         r'conclus[ãa]o\s+do\s+Curso[^§]{0,400}',
         r'CONCLUS[ÃA]O\s+DE\s+CURSO[^§]{0,400}',
         r'confere\s+o\s+t[íi]tulo\s+de[^§]{0,200}',
         r'outorga[^§]{0,120}Diploma[^§]{0,120}']
RXR = re.compile('|'.join(RUIDO), re.I)

def limpa(t):
    return RXR.sub(' ', t)

out = {}
for cnj, v in L.items():
    if not v.get('ok'): continue
    lau = [l for l in v.get('laudos', []) if l['chars'] > 1500]
    if not lau:
        out[cnj] = {'veredito': 'sem_texto', 'f': 0, 'd': 0, 'ev': []}
        continue
    t = limpa(re.sub(r'\s+', ' ', ' '.join(open(l['path'], encoding='utf-8').read() for l in lau)))
    f = d = 0; ev = []
    for rx, w in FAV:
        n = len(re.findall(rx, t, re.I))
        if n: f += w * min(n, 2); ev.append(f'+{w}x{n} {rx[:34]}')
    for rx, w in DES:
        n = len(re.findall(rx, t, re.I))
        if n: d += w * min(n, 2); ev.append(f'-{w}x{n} {rx[:34]}')
    if f and d and abs(f - d) < 4: ver = 'ambiguo'
    elif f > d: ver = 'favoravel'
    elif d > f: ver = 'desfavoravel'
    else: ver = 'ambiguo'
    out[cnj] = {'veredito': ver, 'f': f, 'd': d, 'ev': ev}

json.dump(out, open('mapas/laudo_veredito.json', 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
import collections
print(collections.Counter(v['veredito'] for v in out.values()).most_common())
