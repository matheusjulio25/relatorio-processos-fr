#!/usr/bin/env python3
"""Artifact 'Possibilidade de Exito' — 2 abas: (1) fila de despacho, (2) KPIs do que ja foi decidido."""
import json
from pathlib import Path
D=json.load(open('mapas/kpi_0309.json',encoding='utf-8')); R=D['rows']; K=D['k']
CSS=Path('/tmp/artifact_css.txt').read_text(encoding='utf-8')
def br(x,c=1): return f"{x:.{c}f}".replace('.',',')
cal=K['cal']; af=K['ativos_faixa']; et=K['ext_tipo']
esp=round(sum(cal[f]['pem']/100*af.get(f,0) for f in ('A1','A2','B')))
proj=sum(af.get(f,0) for f in ('A1','A2','B')); cegos=af.get('C',0)+af.get('D',0)
FA={'A1':'Laudo favorável + Tema 187 aplicável','A2':'Laudo favorável','B':'Laudo desfavorável',
    'C':'Perícia não produzida','D':'Laudo nos autos, não lido'}
def conf(n): return 'confiança alta' if n>=30 else ('confiança média' if n>=10 else 'amostra indicativa')
AT=[r for r in R if r['e']=='Ativo']; DEC=[r for r in R if r['d']]
import collections
MAPA=json.load(open('mapas/mapa_174.json',encoding='utf-8'))
MAP2=json.load(open('mapas/mapa_102.json',encoding='utf-8'))
def acao(r):
    m2=MAP2.get(r['c'])
    if m2:
        pr=m2[0]
        if pr.startswith('ATENÇÃO'):  return 'Alerta'
        if pr.startswith('Impugnar'): return 'Impugnar'
        if pr.startswith('Requerer') or pr.startswith('Usar o PA'): return 'Despachar'
        if pr.startswith('Manifestar'): return 'Despachar'
        if pr.startswith('Solicitar'):  return 'Sem perícia'
        if pr.startswith('Ler'):      return 'Ler laudo'
    if r['f'] in ('A1','A2'): return 'Despachar'
    if r['f']=='B':           return 'Impugnar'
    m=MAPA.get(r['c'])
    if not m: return 'Sem perícia'
    pr=m[0]
    if pr=='Impugnar':             return 'Impugnar'
    if pr.startswith('Justificar'):return 'Falta à perícia'
    if pr=='Ler o laudo no PJe':   return 'Ler laudo'
    if pr.startswith('Cobrar'):    return 'Cobrar laudo'
    if pr.startswith('Aguardar'):  return 'No prazo'
    if pr.startswith('Confirmar'): return 'Antifalta'
    if pr.startswith('Solicitar'): return 'Sem perícia'
    return 'Conferir'
for r in R:
    r['ac']=acao(r) if r['e']=='Ativo' else ''
    m=MAP2.get(r['c']) or MAPA.get(r['c'])
    r['pv']=(m[0] if m else ''); r['mv']=(m[1] if m else '')
    r['lp']=1 if r['c'] in MAP2 else 0
AC=collections.Counter(r['ac'] for r in AT)
CONC=json.load(open('mapas/maturidade_0309_final.json',encoding='utf-8'))
CONC={x['cnj']:x for x in CONC if x['rodada']=='03/09/2026'}
n_imp_conc=sum(1 for r in AT if r['ac']=='Impugnar' and CONC.get(r['c'],{}).get('conclusos_em'))
n_des_semman=sum(1 for r in AT if r['ac']=='Despachar' and CONC.get(r['c'],{}).get('laudo_sem_manifestacao'))
for r in R: r['cc']=1 if CONC.get(r['c'],{}).get('conclusos_em') else 0
def card(rot,num,small,sub,f=None,pill=None):
    tag='button' if f else 'div'
    at=f' class="card" data-f="{f}" type="button"' if f else ' class="card"'
    ver='<span class="verlista">Ver a lista</span>' if f else ''
    sm=f'<small>{small}</small>' if small else ''
    pz=f'<span class="chip" style="align-self:flex-start;margin-bottom:6px">{pill}</span>' if pill else ''
    return (f'<{tag}{at}><span class="rot">{rot}</span>{pz}'
            f'<span class="num">{num}{sm}</span><span class="sub">{sub}</span>{ver}</{tag}>')
def barra(f,pref='k'):
    c=cal.get(f); n=c['n'] if c else 0; pem=c['pem'] if c else 0
    return (f'<button class="row" data-f="{pref}:{f}" type="button">'
            f'<span class="lab"><span class="nome">{FA[f]}</span><span class="val">{br(pem)}%</span></span>'
            f'<span class="bar-track"><span class="bar" style="width:{pem:.1f}%"></span></span>'
            f'<span class="pe"><span>n = {n} decididos</span><span>{c["ex"] if c else 0} êxitos</span>'
            f'<span class="chip">{conf(n)}</span></span></button>')
H=[];A=H.append
A('<title>Possibilidade de Êxito</title>')
A(f'<style>{CSS}</style>')
A('''<style>
  .abas { display:flex; gap:0; border-bottom:1px solid var(--rule); margin-bottom:30px; flex-wrap:wrap; }
  .aba { font:inherit; font-family:var(--font-cond); font-size:15px; letter-spacing:.6px;
    text-transform:uppercase; padding:12px 20px; cursor:pointer; background:none; color:var(--ink-muted);
    border:0; border-bottom:3px solid transparent; margin-bottom:-1px; }
  .aba:hover { color:var(--ink-2); }
  .aba[aria-selected="true"] { color:var(--accent); border-bottom-color:var(--accent); font-weight:700; }
  .aba:focus-visible { outline:2px solid var(--accent); outline-offset:-2px; }
  .aba .c { font-size:11px; letter-spacing:0; color:var(--ink-muted); margin-left:7px;
    font-variant-numeric:tabular-nums; }
  .aba[aria-selected="true"] .c { color:var(--accent-soft); }
  .pz { font-size:8.5px; text-transform:uppercase; letter-spacing:1px; padding:1px 5px;
    border:1px solid var(--rule-strong); color:var(--ink-2); white-space:nowrap; }
  td .prov { font-weight:700; color:var(--accent); }
  .ac-imp, .ac-desp, .ac-agu { font-family:var(--font-cond); font-size:13px; letter-spacing:.4px;
    text-transform:uppercase; font-weight:700; white-space:nowrap; }
  .ac-imp { color:#B3261E; } .ac-desp { color:#1E6B45; } .ac-agu { color:var(--ink-muted); }
  @media (prefers-color-scheme: dark) { :root:not([data-theme="light"]) .ac-imp { color:#F2A9A2; }
    :root:not([data-theme="light"]) .ac-desp { color:#8FD3B0; } }
  :root[data-theme="dark"] .ac-imp { color:#F2A9A2; }
  :root[data-theme="dark"] .ac-desp { color:#8FD3B0; }
  td .mot { display:block; font-size:10.5px; color:var(--ink-muted); margin-top:2px; }
</style>''')
A('<style>.capa .marca{flex:1 1 auto}.capa .meta{flex:0 0 auto;text-align:right}</style>')
A('<div class="wrap">')
A(f'''<header class="capa">
  <div class="marca"><p class="escritorio">Fernandes &amp; Rêgo</p>
    <p class="setor">Advogados Associados · Controladoria</p></div>
  <div class="meta"><dl>
    <dt>Apurado em</dt><dd>03/09/2026</dd>
    <dt>A decidir</dt><dd>{len(AT)} processos</dd>
    <dt>Já decididos</dt><dd>{len(DEC)} processos</dd>
  </dl></div></header>''')
A(f'''<div class="abas" role="tablist">
  <button class="aba" role="tab" id="t-desp" aria-controls="p-desp" aria-selected="true" type="button">
    Para despachar<span class="c">{len(AT)}</span></button>
  <button class="aba" role="tab" id="t-kpi" aria-controls="p-kpi" aria-selected="false" type="button">
    Já decidido · KPIs<span class="c">{len(DEC)}</span></button>
</div>''')

# ================= ABA 1 — PARA DESPACHAR =================
A('<div id="p-desp" role="tabpanel" aria-labelledby="t-desp">')
A('<section><div class="sec-head"><span class="sec-num">01</span><h2>Duas providências</h2><span class="reg"></span></div>')
A(f'<p class="sec-intro">O laudo do perito decide o rumo, então a triagem só tem duas saídas: '
  f'<strong>laudo favorável, requer-se o julgamento</strong>; <strong>laudo desfavorável, impugna-se antes</strong>. '
  f'O resto do acervo não tem laudo de perito nos autos — e nesses a providência é <strong>fazer a perícia '
  f'acontecer</strong>. <strong>Clique num número para abrir a lista.</strong></p>')
A('<div class="duo">')
A(card('Impugnar — laudo desfavorável nos autos',str(AC['Impugnar']),'',
       f'{n_imp_conc} já estão conclusos para julgamento','d:Impugnar','48h'))
A(card('Despachar — laudo favorável nos autos',str(AC['Despachar']),'',
       f'{n_des_semman} ainda sem manifestação nossa','d:Despachar','5 dias'))
A('</div>')
A('<div class="cards" style="grid-template-columns:repeat(auto-fit,minmax(158px,1fr));margin-top:12px">')
A(card('Prova social contra o cliente',str(AC['Alerta']),'',
       'rever a estratégia antes de despachar','d:Alerta','48h'))
A(card('Faltou à perícia — risco de extinção',str(AC['Falta à perícia']),'',
       'justificar e pedir redesignação','d:Falta à perícia','48h'))
A(card('Perícia feita, laudo vencido',str(AC['Cobrar laudo']),'',
       'passou de 15 dias úteis — cobrar','d:Cobrar laudo','5 dias'))
A(card('Perícia marcada — garantir presença',str(AC['Antifalta']),'',
       'ligação D-3 e mensagem D-1','d:Antifalta','D-3/D-1'))
A(card('Laudo entregue, ainda por ler',str(AC['Ler laudo']),'',
       'ler e cair numa das duas','d:Ler laudo','5 dias'))
A(card('Sem perícia designada',str(AC['Sem perícia']),'',
       'requerer a designação','d:Sem perícia','5 dias'))
A(card('Laudo ainda no prazo',str(AC['No prazo']),'',
       'perícia recente — só acompanhar','d:No prazo'))
A(card('Sumiram do acervo',str(AC['Conferir']),'',
       'conferir a situação','d:Conferir','48h'))
A('</div>')
A(f'''<div class="nota"><h3>O que a aba de perícias mostrou</h3>
<p>A timeline do processo não revela se há perícia marcada — isso só aparece na <strong>aba de perícias</strong>,
dentro dos autos. Abrindo essa aba nos {AC['Sem perícia']+AC['Cobrar laudo']+AC['Antifalta']+AC['Ler laudo']+AC['Falta à perícia']}
processos sem laudo lido, o quadro mudou: {AC['Cobrar laudo']} tiveram a perícia <strong>há mais de 15 dias úteis e o laudo não foi
juntado</strong>, {AC['Antifalta']} estão com <strong>data marcada</strong> e {AC['Falta à perícia']} registram
<strong>Ausência de Parte</strong>.</p>
<p>Os {AC['Falta à perícia']} que faltaram são a emergência silenciosa: não comparecer é a causa de extinção mais
evitável do acervo, e ainda dá para justificar a falta e pedir redesignação. Nos {AC['Antifalta']} com data marcada,
a providência não é jurídica — é ligar em D-3 e mandar mensagem em D-1.</p>
<p>Só {AC['Sem perícia']} realmente não têm nada designado. Nesses, o que se requer é a designação.</p></div>''')
A('</section>')

A('<section><div class="sec-head"><span class="sec-num">02</span><h2>Tema 187 / TNU nos ativos</h2><span class="reg"></span></div>')
A(f'<p class="sec-intro">A dispensa da perícia social vale quando o INSS negou apenas a deficiência, deixando a renda '
  f'incontroversa. Só os ativos comportam o pedido — e a janela fecha quando o processo é sentenciado.</p>')
A('<div class="cards">')
A(card('Elegíveis e ativos — cabe pedir a dispensa',str(K['t187_ativos']),'',
       f'de {K["t187_total"]} com o perfil no acervo','d:t187'))
A(card('Ativos com laudo favorável — pedir junto com o julgamento',str(K['t187_A1']),'',
       'a combinação mais forte','d:A1t'))
A(card('Alvos de julho já perdidos','6','','de 14 — um transitou sem recurso'))
A('</div>')
A(f'''<div class="nota"><h3>A confusão a não fazer</h3>
<p>Isoladamente o Tema 187 não melhora prognóstico: ele marca justamente os casos em que o INSS negou a
deficiência, onde o laudo tende a ser desfavorável. Só <strong>condicionado a laudo favorável</strong> ele
acrescenta. Pedir a dispensa num processo de laudo desfavorável não adianta — primeiro se impugna o laudo, e a
dispensa fica assentada na mesma peça para o julgamento seguinte.</p></div>''')
A('</section>')

A('<section id="consulta"><div class="sec-head"><span class="sec-num">03</span><h2>Os processos a despachar</h2><span class="reg"></span></div>')
FD=[('d:todos',f'Todos os ativos · {len(AT)}'),
    ('d:Impugnar',f'Impugnar · {AC["Impugnar"]}'),
    ('d:Despachar',f'Despachar · {AC["Despachar"]}'),
    ('d:Alerta',f'Alerta · {AC["Alerta"]}'),
    ('d:Falta à perícia',f'Faltou à perícia · {AC["Falta à perícia"]}'),
    ('d:lidopdf',f'Laudo lido no PDF · {sum(1 for r in AT if r.get("lp"))}'),
    ('d:Cobrar laudo',f'Cobrar laudo · {AC["Cobrar laudo"]}'),
    ('d:No prazo',f'Laudo no prazo · {AC["No prazo"]}'),
    ('d:Antifalta',f'Antifalta · {AC["Antifalta"]}'),
    ('d:Ler laudo',f'Ler laudo · {AC["Ler laudo"]}'),
    ('d:Sem perícia',f'Sem perícia · {AC["Sem perícia"]}'),
    ('d:Conferir',f'Conferir · {AC["Conferir"]}'),
    ('d:t187',f'Tema 187 · {K["t187_ativos"]}'),
    ('d:lido',f'Laudo lido em 03/09 · {sum(1 for r in AT if r["li"])}'),
    ('d:novo',f'Novos no acervo · {sum(1 for r in AT if r["nv"])}')]
A('<div class="filtros">'+''.join(
  f'<button class="fbtn" data-f="{k}" type="button" aria-pressed="{"true" if k=="d:todos" else "false"}">{t}</button>'
  for k,t in FD)+'</div>')
A('<div class="busca"><label for="qd" style="font-size:11px;color:var(--ink-muted)">Buscar</label>'
  '<input id="qd" type="search" placeholder="número do processo ou nome do cliente">'
  '<span class="contagem" id="contd"></span></div>')
A('<div class="tw"><table><caption id="capd">Todos os ativos</caption><thead><tr>'
  '<th>Processo</th><th>Cliente</th><th>Ação</th><th>Prazo</th><th>Providência</th>'
  '<th>Prova nos autos</th><th>T187</th></tr></thead><tbody id="corpod"></tbody></table></div>'
  '<p class="vazio" id="vaziod" hidden>Nenhum processo neste filtro.</p>')
A('</section>')
A('</div>')

# ================= ABA 2 — JA DECIDIDO =================
A('<div id="p-kpi" role="tabpanel" aria-labelledby="t-kpi" hidden>')
A('<section><div class="sec-head"><span class="sec-num">01</span><h2>Os dois indicadores</h2><span class="reg"></span></div>')
A(f'<p class="sec-intro">Estes números vêm só do que <strong>já foi decidido</strong> — {len(DEC)} processos com '
  f'desfecho registrado. Perder no mérito e perder sem chegar ao mérito são fracassos de natureza diferente, '
  f'por isso o KPI é partido em dois.</p>')
A('<div class="cards">')
A(card('PEM · Probabilidade de êxito no mérito',br(K['pem']),'%',
       f"{K['exitos']} êxitos em {K['decididos']} decididos",'k:dec_exito'))
A(card('RESM · Risco de extinção sem mérito',br(K['resm']),'%',
       f"{K['extintos']} em {K['encerrados']} encerrados",'k:extinto'))
A(card('Êxitos esperados no acervo ativo','~'+str(esp),'',
       f'aplicando as taxas aos {proj} projetáveis'))
A('</div>')
A(f'''<div class="nota"><h3>Como o êxito é contado</h3>
<p>Êxito reúne <strong>procedente</strong>, <strong>parcialmente procedente</strong> e <strong>acordo
homologado</strong>. Improcedente é não-êxito. A <strong>extinção sem resolução do mérito</strong> e o mandado de
segurança por mora do INSS ficam <strong>fora do denominador</strong> do PEM — vão para o RESM, que é onde de fato
pertencem.</p>
<p>Base de {K['base']} processos: o acervo inteiro foi varrido em 03/09/2026 ({K['acervo']} processos), as timelines
dos {K['vivos']} vivos foram lidas uma a uma no PJe, e os desfechos vieram do compilado de {K['sent_total']}
sentenças classificadas.</p></div>''')
A('</section>')

A('<section><div class="sec-head"><span class="sec-num">02</span><h2>PEM por faixa de prova</h2><span class="reg"></span></div>')
A('<p class="sec-intro">O laudo do perito judicial é o fator dominante — oito vezes de diferença entre favorável e '
  'desfavorável. Nenhuma outra variável testada (benefício, vara, motivo do indeferimento) chega perto desse poder '
  'de separação.</p>')
A('<div class="chart">'+''.join(barra(f,'k') for f in ('A1','A2','C','B','D'))+'</div>')
A(f'''<div class="nota"><h3>Duas faixas que não são projeção</h3>
<p>“Perícia não produzida” fecha em {br(cal['C']['pem'])}% e “laudo não lido” em {br(cal['D']['pem'])}%, mas essas
taxas <strong>não foram aplicadas</strong> aos ativos correspondentes. Nos decididos, “sem laudo judicial” significa
ter vencido por documento ou acordo — um desfecho; nos ativos, significa prova que ainda não existe. Populações
distintas: herdar a taxa seria viés de sobrevivência.</p></div>''')
A('</section>')

tot_ext=sum(v for k,v in et.items() if k)
A('<section><div class="sec-head"><span class="sec-num">03</span><h2>Onde o processo morre antes do mérito</h2><span class="reg"></span></div>')
A('<p class="sec-intro">O RESM tem causas distintas, e elas não se corrigem no mesmo lugar. Decompô-lo é o que '
  'transforma o indicador em tarefa.</p>')
A('<div class="chart">')
for k_,rot in (('pre_instrucao','Indeferimento da inicial / emenda não cumprida'),
               ('abandono','Abandono ou não comparecimento'),
               ('desistencia','Desistência'),('outros','Outras causas')):
    n=et.get(k_,0); pct=100*n/tot_ext if tot_ext else 0
    A(f'<div class="row"><span class="lab"><span class="nome">{rot}</span><span class="val">{n}</span></span>'
      f'<span class="bar-track"><span class="bar" style="width:{pct:.1f}%"></span></span>'
      f'<span class="pe"><span>{br(pct)}% das extinções da base</span></span></div>')
A('</div>')
A(f'''<div class="nota"><h3>O vazamento maior está antes da perícia</h3>
<p>Olhando <strong>todas as {K['sent_total']} sentenças</strong> já classificadas do escritório, e não só a base
deste painel, <strong>{K['pre_instrucao']} são indeferimento da petição inicial ou extinção por emenda não
cumprida</strong> — {br(K['pre_pct'])}% de tudo que foi sentenciado. Não é derrota de tese nem falta do cliente à
perícia: é documentação que não entrou a tempo.</p>
<p>É o único número deste painel que o escritório resolve sozinho, sem depender de perito, juiz ou INSS — e é maior
que o PEM e o RESM somados em impacto.</p></div>''')
A('</section>')

A('<section id="consultak"><div class="sec-head"><span class="sec-num">04</span><h2>Os processos já decididos</h2><span class="reg"></span></div>')
FK=[('k:todos',f'Todos os decididos · {len(DEC)}'),('k:dec_exito',f'Êxito · {K["exitos"]}'),
    ('k:dec_perda',f'Improcedente · {sum(1 for r in R if r["x"] is False)}'),
    ('k:extinto',f'Extinto sem mérito · {K["extintos"]}'),
    ('k:pre',f'Perdido na emenda · {et.get("pre_instrucao",0)}'),
    ('k:abandono',f'Faltou / abandono · {et.get("abandono",0)}'),
    ('k:A1',f'Faixa A1 · {cal["A1"]["n"]}'),('k:A2',f'Faixa A2 · {cal["A2"]["n"]}'),
    ('k:B',f'Faixa B · {cal["B"]["n"]}')]
A('<div class="filtros">'+''.join(
  f'<button class="fbtn" data-f="{k}" type="button" aria-pressed="{"true" if k=="k:todos" else "false"}">{t}</button>'
  for k,t in FK)+'</div>')
A('<div class="busca"><label for="qk" style="font-size:11px;color:var(--ink-muted)">Buscar</label>'
  '<input id="qk" type="search" placeholder="número do processo ou nome do cliente">'
  '<span class="contagem" id="contk"></span></div>')
A('<div class="tw"><table><caption id="capk">Todos os decididos</caption><thead><tr>'
  '<th>Processo</th><th>Cliente</th><th>Benefício</th><th>Faixa de prova</th>'
  '<th class="n">PEM</th><th>T187</th><th>Desfecho</th></tr></thead>'
  '<tbody id="corpok"></tbody></table></div>'
  '<p class="vazio" id="vaziok" hidden>Nenhum processo neste filtro.</p>')
A('</section>')

A('<section><div class="sec-head"><span class="sec-num">05</span><h2>Calibração e limites</h2><span class="reg"></span></div>')
A('<p class="sec-intro">O PEM é uma <strong>taxa-base condicionada</strong> — a frequência observada de êxito dentro '
  'de cada faixa. Não é modelo preditivo treinado, e não deve ser lido como probabilidade individual de um processo.</p>')
A(f'''<ul>
<li><strong>Calibração:</strong> {K['base']} processos, dos quais {K['decididos']} com mérito decidido. O estado dos
{K['vivos']} vivos foi lido direto no PJe em <strong>03/09/2026</strong>, timeline por timeline.</li>
<li><strong>O que a rodada mudou:</strong> 243 processos nunca haviam sido classificados; 83 laudos médicos e 27
sociais entraram depois de 10/07; 45 processos que constavam ativos mudaram de fase. Recorte antigo não substitui
verificação.</li>
<li><strong>Amostra por faixa:</strong> A1 tem n = {cal['A1']['n']} e é indicativa; A2 e B, com n = {cal['A2']['n']}
e {cal['B']['n']}, sustentam leitura. Reler a cada rodada até passarem de 30.</li>
<li><strong>Fora do denominador:</strong> mandado de segurança por mora do INSS não entra em nenhum dos indicadores;
mede tempo do INSS, não mérito da tese.</li>
<li><strong>Limite conhecido:</strong> {sum(1 for r in R if not r['d'] and r['e']!='Ativo')} processos aparecem
encerrados sem desfecho classificado — a sentença existe mas ainda não foi lida. Estão fora dos denominadores,
não contra o escritório.</li>
</ul>''')
A(f'''<div class="rodape">
<p><strong>Como manter.</strong> Varrer o acervo com <code>bin/dump_acervo.py</code>, reler as timelines com
<code>bin/verificar_estado_cnj.py</code>, extrair os laudos com <code>bin/extrair_laudos_texto.py</code> e recalcular
com <code>bin/kpi_exito_0309.py</code>.</p>
<p>Fernandes &amp; Rêgo Advogados Associados · Documento interno de inteligência jurídica · rodada de 03/09/2026</p>
</div>''')
A('</section>')
A('</div>')
A('</div>')

A('<script type="application/json" id="dados">'+json.dumps(R,ensure_ascii=False,separators=(',',':'))+'</script>')
PEMJS=json.dumps({f:(br(cal[f]['pem'])+'%' if f in cal else '—') for f in 'A1 A2 B C D'.split()},ensure_ascii=False)
A('''<script>
(function () {
  var D = JSON.parse(document.getElementById('dados').textContent);
  var FAIXA = { A1:'Laudo favorável + Tema 187', A2:'Laudo favorável', B:'Laudo desfavorável',
                C:'Perícia não produzida', D:'Laudo não lido' };
  var PEM = __PEM__;
  function esc(s){ return String(s==null?'':s).replace(/[&<>"]/g,function(c){
    return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]; }); }
  function norm(s){ return s.toLowerCase().replace(/[.\\-\\s]/g,''); }

  /* ---------- abas ---------- */
  var abas = [['t-desp','p-desp'],['t-kpi','p-kpi']];
  function verAba(id){
    abas.forEach(function(p){
      var sel = p[0]===id;
      document.getElementById(p[0]).setAttribute('aria-selected', sel?'true':'false');
      document.getElementById(p[1]).hidden = !sel;
    });
  }
  abas.forEach(function(p){
    document.getElementById(p[0]).addEventListener('click',function(){ verAba(p[0]); });
  });

  /* ---------- tabela genérica ---------- */
  function Tabela(cfg){
    var corpo=document.getElementById(cfg.corpo), cap=document.getElementById(cfg.cap);
    var cont=document.getElementById(cfg.cont), vazio=document.getElementById(cfg.vazio);
    var q=document.getElementById(cfg.q), atual=cfg.inicial;
    function render(){
      var f = cfg.filtros[atual] || cfg.filtros[cfg.inicial];
      var termo = norm(q.value.trim());
      var lista = cfg.universo().filter(f.fn);
      if (termo) lista = lista.filter(function(r){
        return r.c.replace(/[.\\-]/g,'').indexOf(termo)>=0 ||
               (r.n && norm(r.n).indexOf(termo)>=0); });
      cap.textContent = f.t + (termo ? ' · busca “'+q.value.trim()+'”' : '');
      cont.textContent = lista.length + (lista.length===1?' processo':' processos');
      vazio.hidden = lista.length>0;
      corpo.innerHTML = lista.sort(cfg.ord).map(cfg.linha).join('');
    }
    this.aplicar=function(nome,rolar){
      if(!cfg.filtros[nome]) return;
      atual=nome;
      cfg.chips().forEach(function(b){
        b.setAttribute('aria-pressed', b.getAttribute('data-f')===nome?'true':'false'); });
      render();
      if(rolar){ document.getElementById(cfg.sec).scrollIntoView({
        behavior: matchMedia('(prefers-reduced-motion: reduce)').matches?'auto':'smooth', block:'start'});
        q.focus({preventScroll:true}); }
    };
    q.addEventListener('input',render);
    render();
  }

  var ativo=function(r){ return r.e==='Ativo'; };

  var TD = new Tabela({
    corpo:'corpod', cap:'capd', cont:'contd', vazio:'vaziod', q:'qd', sec:'consulta', inicial:'d:todos',
    universo:function(){ return D.filter(ativo); },
    chips:function(){ return Array.prototype.slice.call(document.querySelectorAll('#p-desp .fbtn')); },
    ord:function(a,b){ var O={'Alerta':0,'Impugnar':1,'Falta à perícia':2,'Despachar':3,'Cobrar laudo':4,'Antifalta':5,'Ler laudo':6,'Sem perícia':7,'No prazo':8,'Conferir':9};
      return (O[a.ac]||9)-(O[b.ac]||9) || b.cc-a.cc || a.c.localeCompare(b.c); },
    filtros:{
      'd:todos':{t:'Todos os ativos', fn:function(){return true;}},
      'd:Impugnar':{t:'Impugnar — laudo desfavorável nos autos', fn:function(r){return r.ac==='Impugnar';}},
      'd:Despachar':{t:'Despachar — laudo favorável nos autos', fn:function(r){return r.ac==='Despachar';}},
      'd:Alerta':{t:'Prova social adversa — rever a estratégia', fn:function(r){return r.ac==='Alerta';}},
      'd:lidopdf':{t:'Laudo lido no PDF em 03/09/2026', fn:function(r){return r.lp===1;}},
      'd:Falta à perícia':{t:'Ausência de Parte na perícia — justificar e pedir redesignação', fn:function(r){return r.ac==='Falta à perícia';}},
      'd:Cobrar laudo':{t:'Perícia realizada há mais de 15 dias úteis e laudo não juntado', fn:function(r){return r.ac==='Cobrar laudo';}},
      'd:No prazo':{t:'Perícia recente — laudo ainda dentro do prazo de 15 dias úteis', fn:function(r){return r.ac==='No prazo';}},
      'd:Antifalta':{t:'Perícia marcada — garantir o comparecimento', fn:function(r){return r.ac==='Antifalta';}},
      'd:Sem perícia':{t:'Nenhuma perícia designada — requerer a designação', fn:function(r){return r.ac==='Sem perícia';}},
      'd:Ler laudo':{t:'Laudo entregue, ainda por ler', fn:function(r){return r.ac==='Ler laudo';}},
      'd:Conferir':{t:'Constavam ativos em julho e não apareceram no acervo de 03/09', fn:function(r){return r.ac==='Conferir';}},
      'd:t187':{t:'Tema 187 aplicável — ativos', fn:function(r){return r.t===1;}},
      'd:lido':{t:'Laudo lido no inteiro teor em 03/09/2026', fn:function(r){return r.li===1;}},
      'd:novo':{t:'Novos no acervo desde julho', fn:function(r){return r.nv===1;}},
      'd:A1':{t:'Ativos: laudo favorável + Tema 187', fn:function(r){return r.f==='A1';}},
      'd:A1t':{t:'Ativos: Tema 187 + laudo favorável', fn:function(r){return r.f==='A1'&&r.t===1;}},
      'd:A2':{t:'Ativos: laudo favorável', fn:function(r){return r.f==='A2';}},
      'd:B':{t:'Ativos: laudo desfavorável', fn:function(r){return r.f==='B';}},
      'd:C':{t:'Ativos: perícia não produzida', fn:function(r){return r.f==='C';}},
      'd:D':{t:'Ativos: laudo nos autos, não lido', fn:function(r){return r.f==='D';}}
    },
    linha:function(r){
      var cls = (r.ac==='Impugnar'||r.ac==='Falta à perícia'||r.ac==='Alerta') ? 'ac-imp'
                : r.ac==='Despachar' ? 'ac-desp' : 'ac-agu';
      var prov = r.pv || r.p, motv = r.mv || r.mo;
      return '<tr>'+
        '<td class="mono">'+esc(r.c)+'</td>'+
        '<td>'+(r.n?esc(r.n):'<span style="color:var(--ink-muted)">—</span>')+'</td>'+
        '<td><span class="'+cls+'">'+esc(r.ac)+'</span>'+
          (r.cc===1?'<span class="mot">conclusos</span>':'')+'</td>'+
        '<td>'+(r.pz?'<span class="pz">'+esc(r.pz)+'</span>':'')+'</td>'+
        '<td><span class="prov">'+esc(prov)+'</span><span class="mot">'+esc(motv)+'</span></td>'+
        '<td>'+esc(FAIXA[r.f]||'—')+(r.lp===1?' <span class="tag">PDF lido</span>':r.li===1?' <span class="tag">lido</span>':'')+'</td>'+
        '<td>'+(r.t===1?'<span class="tag">sim</span>':'')+'</td>'+
      '</tr>'; }
  });

  var TK = new Tabela({
    corpo:'corpok', cap:'capk', cont:'contk', vazio:'vaziok', q:'qk', sec:'consultak', inicial:'k:todos',
    universo:function(){ return D.filter(function(r){ return r.d; }); },
    chips:function(){ return Array.prototype.slice.call(document.querySelectorAll('#p-kpi .fbtn')); },
    ord:function(a,b){ return a.c.localeCompare(b.c); },
    filtros:{
      'k:todos':{t:'Todos os processos decididos', fn:function(){return true;}},
      'k:dec_exito':{t:'Êxito obtido', fn:function(r){return r.x===true;}},
      'k:dec_perda':{t:'Julgado improcedente', fn:function(r){return r.x===false;}},
      'k:extinto':{t:'Extinto sem resolução do mérito', fn:function(r){return r.d==='Extinto sem mérito';}},
      'k:pre':{t:'Perdido antes da instrução — inicial indeferida ou emenda não cumprida', fn:function(r){return r.te==='pre_instrucao';}},
      'k:abandono':{t:'Abandono ou não comparecimento', fn:function(r){return r.te==='abandono';}},
      'k:A1':{t:'Faixa: laudo favorável + Tema 187', fn:function(r){return r.f==='A1';}},
      'k:A2':{t:'Faixa: laudo favorável', fn:function(r){return r.f==='A2';}},
      'k:B':{t:'Faixa: laudo desfavorável', fn:function(r){return r.f==='B';}},
      'k:C':{t:'Faixa: perícia não produzida', fn:function(r){return r.f==='C';}},
      'k:D':{t:'Faixa: laudo não lido', fn:function(r){return r.f==='D';}}
    },
    linha:function(r){
      return '<tr>'+
        '<td class="mono">'+esc(r.c)+'</td>'+
        '<td>'+(r.n?esc(r.n):'<span style="color:var(--ink-muted)">—</span>')+'</td>'+
        '<td>'+esc(r.b)+'</td>'+
        '<td>'+esc(FAIXA[r.f]||'—')+'</td>'+
        '<td class="n'+(r.f==='A1'||r.f==='A2'||r.f==='B'?' forte':'')+'">'+(PEM[r.f]||'—')+'</td>'+
        '<td>'+(r.t===1?'<span class="tag">sim</span>':'')+'</td>'+
        '<td>'+esc(r.d)+(r.te==='pre_instrucao'?' <span class="tag">emenda</span>':
                         r.te==='abandono'?' <span class="tag">faltou</span>':'')+'</td>'+
      '</tr>'; }
  });

  document.querySelectorAll('[data-f]').forEach(function(el){
    el.addEventListener('click',function(){
      var nome=el.getAttribute('data-f'), rolar=!el.classList.contains('fbtn');
      if(nome.indexOf('d:')===0){ verAba('t-desp'); TD.aplicar(nome,rolar); }
      else { verAba('t-kpi'); TK.aplicar(nome,rolar); }
    });
  });
})();
</script>'''.replace('__PEM__',PEMJS))
Path('relatorios/artifact_exito_0309.html').write_text('\n'.join(H),encoding='utf-8')
print('->relatorios/artifact_exito_0309.html',len('\n'.join(H)),'ch |',len(AT),'ativos |',len(DEC),'decididos')
