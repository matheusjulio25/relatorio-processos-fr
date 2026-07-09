import re, html as _h, glob, sys
sys.path.insert(0, '/Users/matheusjuliorego/relatorio-processos-fr')
from coletor_pje.turmas_recursais import extrair_advogados

for f in sorted(glob.glob('/Users/matheusjuliorego/relatorio-processos-fr/mapas/acordaos_tr/*/*.html')):
    if 'Ac_rd' not in f:
        continue
    raw = open(f, encoding='utf-8').read()
    raw = re.sub(r'<[^>]+>', ' ', raw)
    raw = _h.unescape(raw)
    txt = re.sub(r'\s+', ' ', raw).strip()
    advs = extrair_advogados(txt)
    if advs:
        print(f.split('/')[-2][:40])
        for a in advs:
            print('  ' + a['lado'] + ': ' + a['nome'] + ' (' + a['oab'] + ')')
        print()
