#!/usr/bin/env python3
"""Pré-processa o banco de acórdãos TR para a análise de mercado/êxito:
amostra casos VENCEDORES (procedente/parcial) e PERDIDOS (improcedente) por tema,
com diversidade de relator, e extrai o TEXTO LIMPO (voto/ementa/sentença) para
mapas/_analise/txt/. Gera mapas/_analise/manifest.json + imprime as contagens."""
import json, re, os, time, collections

OUT = "mapas/_analise"; TXT = f"{OUT}/txt"
os.makedirs(TXT, exist_ok=True)

def carrega(fp):
    for _ in range(6):
        try:
            return json.load(open(fp, encoding="utf-8"))
        except Exception:
            time.sleep(0.3)
    return []

dados = []
for n in (1, 3, 2):
    for a in carrega(f"mapas/acordaos_tr_t{n}.json"):
        dados.append(a)

def ftxt(a): return ((a.get("ementa") or "") + " " + (a.get("relatoria") or "")).lower()
def ano(a):
    m = re.search(r"\.(\d{4})\.", a.get("processo", "")); return int(m.group(1)) if m else 0
def comarca(a):
    m = re.search(r"\.4\.05\.(\d{4})", a.get("processo", "")); return m.group(1) if m else "????"
def tema(a):
    t = ftxt(a)
    if re.search(r"autis|\btea\b|espectro|asperger", t): return "TEA"
    if re.search(r"bpc|loas|assistencial|amparo|deficien", t): return "BPC"
    if re.search(r"incapac|aux[ií]lio.?doen|aux[ií]lio.?acident", t): return "INCAPACIDADE"
    if re.search(r"aposentad", t): return "APOSENTADORIA"
    if re.search(r"pens[ãa]o por morte", t): return "PENSAO"
    if re.search(r"rural|segurado especial", t): return "RURAL"
    return None

def html2txt(path, cap=18000):
    try:
        h = open(path, encoding="utf-8", errors="replace").read()
    except Exception:
        return ""
    h = re.sub(r"(?is)<style.*?</style>", " ", h)
    h = re.sub(r"(?is)<script.*?</script>", " ", h)
    t = re.sub(r"<[^>]+>", " ", h)
    t = re.sub(r"&nbsp;|&[a-z]+;", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t[:cap]

def pick(a, *keys):
    for f in (a.get("arquivos") or []):
        bn = os.path.basename(f).lower()
        if any(k in bn for k in keys) and os.path.exists(f):
            return f
    return None

def sample(lst, cap):
    """Amostra com diversidade de relator e recência (round-robin entre relatores)."""
    byrel = collections.defaultdict(list)
    for a in lst:
        byrel[a.get("relator") or "?"].append(a)
    for g in byrel.values():
        g.sort(key=lambda a: -ano(a))
    grupos = sorted(byrel.values(), key=lambda g: -len(g))
    out, i = [], 0
    while len(out) < cap and any(grupos):
        g = grupos[i % len(grupos)]
        if g:
            out.append(g.pop(0))
        i += 1
        if i > 10000:
            break
        grupos = [g for g in grupos if g] or []
        if not grupos:
            break
    return out[:cap]

def build(a):
    docs = [("VOTO", pick(a, "voto")), ("EMENTA", pick(a, "ementa")),
            ("SENTENCA", pick(a, "senten")), ("ACORDAO", pick(a, "ac_rd", "acord", "decis"))]
    files = []
    for tag, p in docs:
        if not p:
            continue
        txt = html2txt(p)
        if txt and len(txt) > 120:
            outp = f"{TXT}/{a['processo'].replace('/', '_').replace('.', '_')}_{tag}.txt"
            with open(outp, "w", encoding="utf-8") as fh:
                fh.write(f"[{tag}] processo={a['processo']} relator={a.get('relator')} "
                         f"resultado={a.get('resultado')} comarca={comarca(a)} ano={ano(a)}\n\n{txt}")
            files.append(outp)
    return {"processo": a["processo"], "relator": a.get("relator"), "comarca": comarca(a),
            "ano": ano(a), "resultado": a.get("resultado"), "files": files}

WIN = {"PROCEDENTE", "PARCIALMENTE_PROCEDENTE"}
THEMES = ["BPC", "TEA", "INCAPACIDADE", "APOSENTADORIA", "PENSAO", "RURAL"]
N_WIN, N_LOSS = 30, 12
manifest, counts = {}, {}
for tm in THEMES:
    pool = [a for a in dados if tema(a) == tm]
    wins = [a for a in pool if a.get("resultado") in WIN]
    losses = [a for a in pool if a.get("resultado") == "IMPROCEDENTE"]
    wi = [x for x in (build(a) for a in sample(wins, N_WIN)) if x["files"]]
    li = [x for x in (build(a) for a in sample(losses, N_LOSS)) if x["files"]]
    manifest[tm] = {"wins": wi, "losses": li,
                    "total_wins": len(wins), "total_losses": len(losses)}
    counts[tm] = {"wins": len(wi), "losses": len(li),
                  "total_wins": len(wins), "total_losses": len(losses)}

json.dump(manifest, open(f"{OUT}/manifest.json", "w", encoding="utf-8"),
          ensure_ascii=False, indent=1)
print("MANIFEST:", f"{OUT}/manifest.json")
print("COUNTS_JSON_START")
print(json.dumps(counts, ensure_ascii=False))
print("COUNTS_JSON_END")
for tm in THEMES:
    c = counts[tm]
    print(f"  {tm}: amostra venc {c['wins']}/{c['total_wins']} | perd {c['losses']}/{c['total_losses']}")
