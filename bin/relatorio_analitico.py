#!/usr/bin/env python3
"""Relatório analítico da triagem de maturidade (JEF/PE) — identidade Fernandes & Rêgo.

Lê as análises da inteligência (journal do workflow ou mapas/analise_cnj_full.json)
+ a pauta (nome/órgão) e produz um .docx analítico (pandoc + bin/brandear_docx.py):
panorama, ação imediata, revisar, Tema 187, perícia, recursos, cumprimento, e
padrões de juízes e peritos. Copia p/ o Drive Controladoria.

Uso: python3 bin/relatorio_analitico.py [journal.jsonl|analise.json]
"""
from __future__ import annotations
import glob
import json
import re
import shutil
import subprocess
import sys
import unicodedata


def nome_canonico(s):
    """Condensa variações tipográficas do mesmo juiz/perito em UM nome:
    remove parênteses/registro/título, acentos e caixa; evita dados falsos."""
    if not s:
        return ""
    base = re.split(r"[(—:/]| - |,|;", s)[0]
    base = unicodedata.normalize("NFKD", base).encode("ascii", "ignore").decode()
    base = re.sub(r"(?i)\b(juiz|juiza|federal|titular|substituto|dr|dra|medico|medica|"
                  r"perito|perita|pericia|assistente|social|forense|nomeado|nomeada|do|juizo)\b", " ", base)
    base = re.sub(r"[^A-Za-z ]", " ", base)
    base = re.sub(r"\s+", " ", base).strip()
    # descarta o que não é nome de pessoa (sobra de parsing)
    if re.search(r"(?i)(\bvara\b|nominad|identificad|autos|consultad|senten|corpo|texto|inteiro|teor|\bnome\b)", base):
        return ""
    if len(base.split()) < 2 or len(base) < 6:
        return ""
    return base.title()
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
PAUTA = BASE / "mapas" / "pericias_por_processo.json"
REL = BASE / "relatorios"
LOGO = REL / "assets" / "logo_fr.png"
DRIVE = Path("/Users/matheusjuliorego/Library/CloudStorage/"
             "GoogleDrive-matheus@julioregoadv.com/Drives compartilhados/"
             "Controladoria - Planilhas de Controle")


def _deep(o):
    if isinstance(o, dict):
        if "estado_processo" in o:
            return o
        for v in o.values():
            r = _deep(v)
            if r:
                return r
    if isinstance(o, str):
        try:
            return _deep(json.loads(o))
        except Exception:
            return None
    return None


def carregar(src):
    by = {}
    if src.endswith(".jsonl"):
        for ln in open(src, encoding="utf-8"):
            try:
                d = json.loads(ln)
            except Exception:
                continue
            if d.get("type") == "result":
                c = _deep(d)
                if c and c.get("cnj"):
                    by[c["cnj"]] = c
    else:
        for c in json.load(open(src, encoding="utf-8")):
            if c.get("cnj"):
                by[c["cnj"]] = c
    return list(by.values())


def fav_bucket(a):
    if a.get("despachar_agora") is True:
        lr = a.get("resultado_laudo")
        if lr == "favoravel":
            return "despachar_fav"
        if lr in ("desfavoravel", "inconclusivo", "nao_verificado"):
            return "revisar"
        return "despachar_tema187"
    est = a.get("estado_processo")
    return est


def cl(s, n=110):
    return re.sub(r"\s+", " ", (s or "")).strip()[:n]


def main():
    src = sys.argv[1] if len(sys.argv) > 1 else ""
    if not src:
        c = glob.glob("/Users/matheusjuliorego/.claude/projects/*/subagents/workflows/*/journal.jsonl")
        c.sort(key=lambda p: Path(p).stat().st_mtime)
        src = c[-1] if c else ""
    A = carregar(src) if src and Path(src).exists() else []
    pauta = json.loads(PAUTA.read_text(encoding="utf-8"))
    def nome(cnj): return (pauta.get(cnj, {}) or {}).get("cliente", "")

    for a in A:
        a["_b"] = fav_bucket(a)
    n = len(A)
    B = Counter(a["_b"] for a in A)
    hoje = date.today().strftime("%d/%m/%Y")

    L = []
    L.append(f"**Escritório:** Fernandes & Rêgo Advogados Associados  ")
    L.append(f"**Data:** {hoje}  · **Processos analisados:** {n} (JEF/PE, 1º grau)  ")
    L.append(f"**Fonte:** pauta de perícia + leitura por IA do detalhe de cada processo (timeline, laudo do perito judicial, sentença, indeferimento).")
    L.append("")
    L.append("## 1. Panorama")
    L.append("")
    L.append("| Situação | Qtd |")
    L.append("|---|---:|")
    ordem = [("despachar_fav", "DESPACHAR — laudo favorável"),
             ("despachar_tema187", "DESPACHAR — sem laudo (Tema 187)"),
             ("revisar", "REVISAR antes — laudo adverso"),
             ("ativo_sem_sentenca", "Ativo, sem sentença (aguardando)"),
             ("em_recurso", "Em recurso (Turma)"),
             ("cumprimento_sentenca", "Cumprimento de sentença"),
             ("sentenciado", "Sentenciado"),
             ("arquivado_extinto", "Arquivado/extinto")]
    for k, lab in ordem:
        if B.get(k):
            L.append(f"| {lab} | {B[k]} |")
    L.append("")
    desp = B.get("despachar_fav", 0) + B.get("despachar_tema187", 0)
    L.append(f"**Leitura executiva:** de {n} processos, **{desp} estão prontos para despacho imediato** "
             f"(requerer julgamento), **{B.get('revisar',0)} exigem impugnação do laudo antes** de qualquer "
             f"pedido de julgamento, e o restante está em fases que não comportam despacho agora "
             f"(recurso, cumprimento, arquivados) ou aguardando prova.")
    L.append("")

    def tabela(bucket_keys, extra=("proxima_diligencia",)):
        out = ["| CNJ | Cliente | Benefício | Laudo | Próxima diligência |", "|---|---|---|---|---|"]
        for a in A:
            if a["_b"] in bucket_keys:
                out.append(f"| {a['cnj']} | {cl(nome(a['cnj']),22)} | {a.get('classe_beneficio','')} "
                           f"| {a.get('resultado_laudo','')} | {cl(a.get('proxima_diligencia',''),140)} |")
        return out if len(out) > 2 else ["_Nenhum._"]

    L.append("## 2. Ação imediata — DESPACHAR para julgamento")
    L.append("")
    L.append("Instrução encerrada e prognóstico favorável. Requerer julgamento (procedência).")
    L.append("")
    L += tabela({"despachar_fav", "despachar_tema187"})
    L.append("")
    L.append("## 3. REVISAR antes — laudo adverso (NÃO despachar)")
    L.append("")
    L.append("Instrução formalmente completa, mas o laudo do perito judicial é desfavorável/dúbio. "
             "Requerer julgamento aqui = improcedência. Ação correta: **impugnar o laudo** (quesitos, "
             "esclarecimentos, nova perícia).")
    L.append("")
    L += tabela({"revisar"})
    L.append("")

    # Tema 187
    t187 = [a for a in A if a.get("dispensa_social_tema187") is True]
    indf_def = [a for a in A if a.get("motivo_indeferimento") == "deficiencia"]
    L.append("## 4. Oportunidade Tema 187/TNU — dispensa da perícia social")
    L.append("")
    L.append(f"Em **{len(indf_def)} processos** o indeferimento administrativo foi por **deficiência** "
             f"(renda incontroversa); em **{len(t187)}** a IA concluiu que a **perícia social é dispensável** "
             "pelo Tema 187/TNU. Nesses, havendo perícia médica favorável, requerer julgamento sem esperar a social.")
    L.append("")

    # Juízes
    jz = defaultdict(Counter)
    for a in A:
        j = nome_canonico(a.get("juiz", ""))
        if j and "identificado" not in j.lower() and a.get("resultado_sentenca") not in (None, "sem_sentenca", "nao_verificado"):
            jz[j][a["resultado_sentenca"]] += 1
    L.append("## 5. Padrões de JUÍZES (dos que já sentenciaram)")
    L.append("")
    if jz:
        L.append("| Juiz | Proced. | Improc. | Extinção | Homolog. | Total |")
        L.append("|---|---:|---:|---:|---:|---:|")
        for j, c in sorted(jz.items(), key=lambda kv: -sum(kv[1].values())):
            tot = sum(c.values())
            L.append(f"| {j} | {c.get('procedente',0)+c.get('parcialmente_procedente',0)} | "
                     f"{c.get('improcedente',0)} | {c.get('extincao_sem_merito',0)} | {c.get('homologacao',0)} | {tot} |")
    else:
        L.append("_Sem dados suficientes._")
    L.append("")

    # Peritos
    pr = defaultdict(Counter)
    for a in A:
        p = nome_canonico(a.get("perito", ""))
        if p and "identificado" not in p.lower() and a.get("resultado_laudo") in ("favoravel", "desfavoravel"):
            pr[p][a["resultado_laudo"]] += 1
    L.append("## 6. Padrões de PERITOS (laudo favorável × desfavorável)")
    L.append("")
    if pr:
        L.append("| Perito | Favorável | Desfavorável | Total |")
        L.append("|---|---:|---:|---:|")
        for p, c in sorted(pr.items(), key=lambda kv: -sum(kv[1].values()))[:25]:
            L.append(f"| {p} | {c.get('favoravel',0)} | {c.get('desfavoravel',0)} | {sum(c.values())} |")
    else:
        L.append("_Sem dados suficientes._")
    L.append("")

    L.append("## 7. Recomendações priorizadas")
    L.append("")
    L.append(f"1. **Despachar hoje** os {desp} prontos (Seção 2) — requerimento de julgamento.")
    L.append(f"2. **Impugnar laudo** nos {B.get('revisar',0)} da Seção 3 antes de qualquer julgamento.")
    L.append(f"3. **Aplicar Tema 187** nos casos da Seção 4 para destravar sem esperar a perícia social.")
    L.append("4. **Conferir prazos de recurso** nos sentenciados improcedentes e acompanhar os em recurso.")
    L.append("5. **Cobrar/monitorar** perícias designadas não realizadas e cumprimentos (RPV) pendentes.")
    L.append("")

    # ---------------- Camada operacional (Legal Ops) ----------------
    desp = B.get("despachar_fav", 0) + B.get("despachar_tema187", 0)
    rev = B.get("revisar", 0)
    recurso = B.get("em_recurso", 0)
    cumpr = B.get("cumprimento_sentenca", 0)
    arq = B.get("arquivado_extinto", 0)
    aguard_social = sum(1 for a in A if a.get("estado_processo") == "ativo_sem_sentenca"
                        and a.get("pericia_social") in ("designada_pendente", "nao_ha")
                        and a.get("classe_beneficio") == "bpc_deficiencia"
                        and not a.get("dispensa_social_tema187"))
    sent_improc = sum(1 for a in A if a.get("estado_processo") == "sentenciado"
                      and a.get("resultado_sentenca") == "improcedente")

    L.append("# Camada Operacional — Legal Ops (Controladoria)")
    L.append("")
    L.append("## 8. Diagnóstico operacional")
    L.append("")
    L.append("- **O que é:** triagem de acervo por maturidade para julgamento, convertida em fila de ação.")
    L.append("- **Classificação:** operacional (governança do acervo) — não é problema de mérito jurídico isolado.")
    L.append("- **Causa-raiz do ruído anterior:** ausência de leitura do estado real do processo (contagem de perícia da pauta marcava arquivados como \"maduros\"). Corrigido: decisão por leitura do inteiro teor.")
    L.append(f"- **Risco se não tratar:** perda de janela de despacho nos {desp} maduros; **improcedência** ao despachar os {rev} de laudo adverso; e **encerramento por não comparecimento** nos {aguard_social} aguardando perícia social (48,1% dos encerramentos do escritório têm essa causa).")
    L.append("")
    L.append("## 9. Matriz RACI por fila (dono · substituto · registro)")
    L.append("")
    L.append("| Fila | Ação | Responsável | Substituto | Registro | Aprova |")
    L.append("|---|---|---|---|---|---|")
    L.append("| Despachar agora | Peticionar requerimento de julgamento | Advogado da pasta | Marília | Legal One | Matheus |")
    L.append("| Revisar (laudo adverso) | Impugnar laudo / quesitos / nova perícia | Advogado da pasta | Max | Legal One | Matheus |")
    L.append("| Tema 187 | Requerer dispensa da social + julgamento | Advogado da pasta | Wendel | Legal One | — |")
    L.append("| Aguardando perícia social | Cobrar designação + protocolo D-3/D-1 | Patrícia | Maria Eduarda | Planilha de diligências | — |")
    L.append("| Em recurso | Conferir prazo / memoriais | Advogado da pasta | Tiago | Legal One | — |")
    L.append("| Cumprimento | Acompanhar cálculos / RPV | Antônio | Maria Eduarda | Legal One | — |")
    L.append("| Sentenciado improcedente | Avaliar recurso no prazo | Advogado da pasta | Marília | Legal One | Matheus |")
    L.append("| Arquivado | Avaliar novo requerimento/ação | Érika | — | Legal One | — |")
    L.append("| Consolidação/controle | Manter a esteira e a pauta | Letícia (Gestora) | — | Planilha Controladoria | Matheus |")
    L.append("")
    L.append("## 10. SLA por fila")
    L.append("")
    L.append("| Fila | Gatilho de entrada | Critério de saída | SLA |")
    L.append("|---|---|---|---|")
    L.append("| Despachar agora | Instrução completa + laudo favorável | Petição de julgamento protocolada | **48h** |")
    L.append("| Revisar (laudo adverso) | Laudo desfavorável/dúbio juntado | Impugnação protocolada | **5 dias** (ou prazo do ato) |")
    L.append("| Tema 187 | Indeferimento por deficiência + médica favorável | Petição Tema 187 protocolada | **72h** |")
    L.append("| Aguardando perícia social | Perícia designada/não realizada | Perícia realizada e laudo juntado | Cobrança em **48h**; protocolo D-3/D-1 |")
    L.append("| Sentenciado improcedente | Publicação da sentença | Recurso interposto ou ciência de não recorrer | **dentro do prazo recursal** (conferir imediatamente) |")
    L.append("| Cumprimento | Sentença procedente transitada | RPV/implantação confirmada | Acompanhamento **semanal** |")
    L.append("")
    L.append("## 11. Fluxo de despacho (TO-BE)")
    L.append("")
    L.append("1. Controladoria abre a planilha por fila (esta análise).")
    L.append("2. Advogado da pasta valida o caso da fila **Despachar agora** → protocola requerimento de julgamento (SLA 48h) → registra no Legal One.")
    L.append("3. Fila **Revisar**: advogado protocola impugnação/quesitos antes de qualquer pedido de julgamento.")
    L.append("4. Fila **Tema 187**: advogado peticiona dispensa da social + julgamento.")
    L.append("5. Fila **Aguardando social**: Patrícia dispara cobrança de designação e aplica protocolo D-3/D-1 de comparecimento.")
    L.append("6. Letícia consolida semanalmente e leva pendências à pauta; Matheus aprova despachos sensíveis.")
    L.append("")
    L.append("## 12. Checklist por fila")
    L.append("")
    L.append("**Despachar agora:** ( ) estado = ativo sem sentença · ( ) perícias exigidas realizadas · ( ) laudo do perito judicial FAVORÁVEL · ( ) sem pendência de impugnação · ( ) petição de julgamento protocolada · ( ) registrado no Legal One.")
    L.append("")
    L.append("**Revisar (laudo adverso):** ( ) laudo lido · ( ) pontos de impugnação (quesitos/omissões/CID) · ( ) pedido de esclarecimento ou nova perícia · ( ) NÃO requerer julgamento antes.")
    L.append("")
    L.append("**Tema 187:** ( ) indeferimento administrativo foi por deficiência · ( ) renda incontroversa · ( ) perícia médica favorável · ( ) petição citando Tema 187/TNU.")
    L.append("")
    L.append("**Aguardando perícia social (protocolo antifalta — 48,1%):** ( ) ligação **D-3** · ( ) mensagem **D-1** (ChatGuru: data/hora/local/documentos) · ( ) confirmação na manhã · ( ) registro compareceu/não + motivo na planilha de diligências.")
    L.append("")
    L.append("## 13. KPIs da esteira de julgamento")
    L.append("")
    L.append("| KPI | Meta | Frequência | Fonte |")
    L.append("|---|---|---|---|")
    L.append("| Maduros despachados / maduros identificados | 100% em 7 dias | Semanal | Planilha Controladoria |")
    L.append("| Tempo médio até o despacho | ≤ 48h | Semanal | Legal One |")
    L.append("| Impugnações protocoladas / fila Revisar | 100% no prazo | Semanal | Legal One |")
    L.append("| Casos Tema 187 peticionados | 100% dos elegíveis | Mensal | Planilha |")
    L.append("| Taxa de não comparecimento à perícia | ↓ (< meta) | Mensal | Planilha de diligências |")
    L.append("")
    L.append("## 14. Pauta de reunião — Controladoria (semanal)")
    L.append("")
    L.append("1. Despachos da semana (fila 1) e bloqueios.")
    L.append("2. Impugnações pendentes (fila Revisar) e prazos.")
    L.append("3. Perícias designadas: protocolo D-3/D-1 e faltas.")
    L.append("4. Recursos com prazo em curso (atenção ao sentenciado improcedente).")
    L.append("5. Cumprimentos/RPV em andamento.")
    L.append("6. KPIs da esteira.")
    L.append("")
    L.append("## 15. Próximos passos")
    L.append("")
    L.append(f"- **24h:** conferir o prazo do sentenciado improcedente ({sent_improc}); iniciar os {desp} despachos.")
    L.append(f"- **7 dias:** concluir os {desp} despachos + as {rev} impugnações; peticionar os Tema 187 elegíveis; disparar cobrança/protocolo nos {aguard_social} de perícia social.")
    L.append(f"- **30 dias:** rodar a esteira semanal, medir os KPIs, e reprocessar o acervo (nova rodada da análise) para atualizar as filas.")
    L.append("")
    L.append("> _Análise assistida por IA sobre o inteiro teor de cada processo; a decisão final de despacho é do advogado responsável. Camada operacional conforme Legal Ops — Fernandes & Rêgo._")

    md = REL / "relatorio_analitico.md"
    md.write_text("\n".join(L), encoding="utf-8")
    base_docx = REL / "_base_analitico.docx"
    final_docx = REL / "Relatorio_Analitico_Maturidade.docx"
    subprocess.run(["pandoc", str(md), "-o", str(base_docx), "--toc", "--toc-depth=2",
                    "-V", "lang=pt-BR"], check=True)
    subprocess.run(["python3", str(BASE / "bin" / "relatorio_fr_docx.py"),
                    str(base_docx), str(final_docx), str(LOGO),
                    "Triagem de Maturidade para Julgamento",
                    "Relatório Analítico · Controladoria — Fernandes & Rêgo",
                    hoje], check=True)
    base_docx.unlink(missing_ok=True)
    print(f"[rel] {final_docx}")
    if DRIVE.exists():
        shutil.copy2(final_docx, DRIVE / final_docx.name)
        print(f"[drive] {DRIVE / final_docx.name}")


if __name__ == "__main__":
    main()
