#!/usr/bin/env python3
"""Análise estatística do acervo (JEF/PE) a partir das análises da IA.
Gera .docx com identidade do escritório e imprime os destaques.
Uso: python3 bin/analise_estatistica.py
"""
from __future__ import annotations
import json
import re
import shutil
import subprocess
import unicodedata
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
A = json.load(open(BASE / "mapas" / "analise_cnj_full.json", encoding="utf-8"))
REL = BASE / "relatorios"
LOGO = REL / "assets" / "logo_fr.png"
DRIVE = Path("/Users/matheusjuliorego/Library/CloudStorage/"
             "GoogleDrive-matheus@julioregoadv.com/Drives compartilhados/"
             "Controladoria - Planilhas de Controle")


def canon(s):
    if not s:
        return ""
    b = re.split(r"[(—:/]| - |,|;", s)[0]
    b = unicodedata.normalize("NFKD", b).encode("ascii", "ignore").decode()
    b = re.sub(r"(?i)\b(juiz|juiza|federal|titular|substituto|dr|dra|medico|medica|perito|perita|"
               r"pericia|assistente|social|forense|nomeado|nomeada|do|juizo)\b", " ", b)
    b = re.sub(r"[^A-Za-z ]", " ", b)
    b = re.sub(r"\s+", " ", b).strip()
    if re.search(r"(?i)(\bvara\b|nominad|identificad|autos|consultad|senten|corpo|texto|inteiro|teor|\bnome\b)", b):
        return ""
    return b.title() if (len(b.split()) >= 2 and len(b) >= 6) else ""


def vara(a):
    t = " ".join(str(a.get(k, "") or "") for k in ("juiz", "fundamento", "proxima_diligencia"))
    m = re.search(r"(\d{1,2})[ªa]?\s*Vara", t)
    return f"{m.group(1)}ª Vara" if m else "n/d"


N = len(A)
COM_SENT = [a for a in A if a.get("resultado_sentenca") not in (None, "sem_sentenca", "nao_verificado")]
FAV = {"procedente", "parcialmente_procedente"}


def pct(x, base):
    return f"{100*x/base:.0f}%" if base else "—"


L = []
L.append("**Escritório:** Fernandes & Rêgo Advogados Associados  ")
L.append(f"**Data:** {date.today().strftime('%d/%m/%Y')}  · **Base:** {N} processos (JEF/PE) analisados por IA sobre o inteiro teor.")
L.append("")

# 1. Estado
L.append("## 1. Composição do acervo por estado")
L.append("")
L.append("| Estado | Qtd | % |")
L.append("|---|---:|---:|")
est = Counter(a["estado_processo"] for a in A)
for k, v in est.most_common():
    L.append(f"| {k} | {v} | {pct(v,N)} |")
L.append("")

# 2. Desfecho dos sentenciados
proc = sum(1 for a in COM_SENT if a["resultado_sentenca"] in FAV)
improc = sum(1 for a in COM_SENT if a["resultado_sentenca"] == "improcedente")
ext = sum(1 for a in COM_SENT if a["resultado_sentenca"] == "extincao_sem_merito")
hom = sum(1 for a in COM_SENT if a["resultado_sentenca"] == "homologacao")
merito = proc + improc
L.append("## 2. Desfecho dos processos com sentença")
L.append("")
L.append(f"- Sentenciados: **{len(COM_SENT)}** ({pct(len(COM_SENT),N)} do acervo).")
L.append(f"- Procedente/parcial: **{proc}** · Improcedente: **{improc}** · Extinção s/ mérito: **{ext}** · Homologação (acordo): **{hom}**.")
L.append(f"- **Taxa de êxito no mérito** (procedência / [procedência+improcedência]): **{pct(proc,merito)}** ({proc}/{merito}).")
L.append("")

# 3. Por vara
L.append("## 3. Por vara (volume e êxito)")
L.append("")
L.append("| Vara | Processos | Sentenciados | Procedência (mérito) |")
L.append("|---|---:|---:|---:|")
vc = defaultdict(list)
for a in A:
    vc[vara(a)].append(a)
for v, lst in sorted(vc.items(), key=lambda kv: -len(kv[1])):
    s = [x for x in lst if x.get("resultado_sentenca") in FAV or x.get("resultado_sentenca") == "improcedente"]
    p = sum(1 for x in s if x["resultado_sentenca"] in FAV)
    L.append(f"| {v} | {len(lst)} | {sum(1 for x in lst if x in COM_SENT)} | {pct(p,len(s))} ({p}/{len(s)}) |")
L.append("")

# 4. Benefício
L.append("## 4. Por espécie de benefício")
L.append("")
L.append("| Benefício | Qtd | % |")
L.append("|---|---:|---:|")
for k, v in Counter(a.get("classe_beneficio") for a in A).most_common():
    L.append(f"| {k} | {v} | {pct(v,N)} |")
L.append("")

# 5. Laudo judicial
lc = Counter(a.get("resultado_laudo") for a in A)
com_laudo = lc.get("favoravel", 0) + lc.get("desfavoravel", 0)
L.append("## 5. Laudo do perito judicial")
L.append("")
L.append(f"- Favorável: **{lc.get('favoravel',0)}** · Desfavorável: **{lc.get('desfavoravel',0)}** · "
         f"Sem laudo judicial: {lc.get('sem_laudo_judicial',0)} · Não verificado: {lc.get('nao_verificado',0)}.")
L.append(f"- **Taxa de laudo favorável** (dos que têm laudo): **{pct(lc.get('favoravel',0),com_laudo)}** ({lc.get('favoravel',0)}/{com_laudo}).")
L.append("")

# 6. Cruzamento laudo x sentença
L.append("## 6. Correlação laudo × sentença (força da perícia)")
L.append("")
cross = defaultdict(Counter)
for a in COM_SENT:
    lr = a.get("resultado_laudo")
    if lr in ("favoravel", "desfavoravel"):
        cross[lr]["procedente" if a["resultado_sentenca"] in FAV else "outro"] += 1
L.append("| Laudo | Sentença procedente | Não procedente | % procedência |")
L.append("|---|---:|---:|---:|")
for lr in ("favoravel", "desfavoravel"):
    c = cross[lr]
    tot = c["procedente"] + c["outro"]
    L.append(f"| {lr} | {c['procedente']} | {c['outro']} | {pct(c['procedente'],tot)} |")
L.append("")
L.append("> Leitura: mede o quanto o laudo do perito judicial \"puxa\" o resultado — base para priorizar impugnação onde o laudo é adverso.")
L.append("")

# 7. Tema 187
ind = Counter(a.get("motivo_indeferimento") for a in A)
t187 = sum(1 for a in A if a.get("dispensa_social_tema187") is True)
L.append("## 7. Tema 187/TNU")
L.append("")
L.append(f"- Indeferimento por deficiência (renda incontroversa): **{ind.get('deficiencia',0)}** · por renda/ambos: {ind.get('renda_miserabilidade',0)+ind.get('ambos',0)} · não identificado: {ind.get('nao_identificado',0)}.")
L.append(f"- Casos com **dispensa da perícia social** reconhecível: **{t187}** ({pct(t187,N)}).")
L.append("")

# 8. Peritos
L.append("## 8. Peritos — taxa de laudo desfavorável (mín. 4 laudos)")
L.append("")
pr = defaultdict(Counter)
for a in A:
    p = canon(a.get("perito", ""))
    if p and a.get("resultado_laudo") in ("favoravel", "desfavoravel"):
        pr[p][a["resultado_laudo"]] += 1
L.append("| Perito | Favorável | Desfavorável | % desfav. |")
L.append("|---|---:|---:|---:|")
for p, c in sorted(pr.items(), key=lambda kv: -(kv[1]['desfavoravel']/max(sum(kv[1].values()),1))):
    tot = sum(c.values())
    if tot >= 4:
        L.append(f"| {p} | {c['favoravel']} | {c['desfavoravel']} | {pct(c['desfavoravel'],tot)} |")
L.append("")

# 9. Juízes
L.append("## 9. Juízes — desfecho de mérito (nominados)")
L.append("")
jz = defaultdict(Counter)
for a in COM_SENT:
    j = canon(a.get("juiz", ""))
    if j:
        jz[j][a["resultado_sentenca"]] += 1
L.append("| Juiz | Procedente | Improcedente | Extinção | Homolog. |")
L.append("|---|---:|---:|---:|---:|")
for j, c in sorted(jz.items(), key=lambda kv: -sum(kv[1].values())):
    L.append(f"| {j} | {c.get('procedente',0)+c.get('parcialmente_procedente',0)} | {c.get('improcedente',0)} | {c.get('extincao_sem_merito',0)} | {c.get('homologacao',0)} |")
L.append("")
L.append("> Nota: sentenças com assinatura eletrônica sem nome no corpo caem em \"não nominado\" e não entram aqui.")
L.append("")

md = REL / "analise_estatistica.md"
md.write_text("\n".join(L), encoding="utf-8")
base_docx = REL / "_base_est.docx"
final = REL / "Analise_Estatistica_Acervo.docx"
subprocess.run(["pandoc", str(md), "-o", str(base_docx), "--toc", "--toc-depth=2", "-V", "lang=pt-BR"], check=True)
subprocess.run(["python3", str(BASE / "bin" / "relatorio_fr_docx.py"), str(base_docx), str(final), str(LOGO),
                "Análise Estatística do Acervo", "Controladoria — Fernandes & Rêgo", date.today().strftime("%d/%m/%Y")], check=True)
base_docx.unlink(missing_ok=True)
print("OK:", final)
if DRIVE.exists():
    shutil.copy2(final, DRIVE / final.name)
    print("[drive]", DRIVE / final.name)

# destaques no terminal
print("\n=== DESTAQUES ===")
print(f"acervo: {N} | sentenciados: {len(COM_SENT)} ({pct(len(COM_SENT),N)}) | êxito mérito: {pct(proc,merito)} ({proc}/{merito})")
print(f"laudo favorável (dos c/ laudo): {pct(lc.get('favoravel',0),com_laudo)} | Tema 187 dispensa: {t187}")
