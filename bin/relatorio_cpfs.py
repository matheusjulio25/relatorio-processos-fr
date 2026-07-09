#!/usr/bin/env python3
"""Gera o relatório da triagem por CPF em 3 grupos + CSV, com a identidade do
escritório (pandoc + bin/brandear_docx.py). Lê mapas/consulta_cpfs.json.

Grupos:
  1) COM PROCESSO (ativo)         -> status com_processo
  2) ARQUIVADOS DEFINITIVAMENTE   -> status arquivado_definitivo
  3) SEM PROCESSO (não ajuizados) -> status sem_processo
  4) NÃO CONSULTADOS (falha)      -> CPFs da lista ausentes do checkpoint

Uso: python3 bin/relatorio_cpfs.py
"""
from __future__ import annotations

import csv
import json
import re
import subprocess
from datetime import date
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
OUT_JSON = BASE / "mapas" / "consulta_cpfs.json"
CPFS_FP = BASE / "mapas" / "cpfs_consulta.txt"
REL_DIR = BASE / "relatorios"
LOGO = REL_DIR / "assets" / "logo_fr.png"


def fmt_cpf(d: str) -> str:
    d = re.sub(r"\D", "", d)
    return f"{d[:3]}.{d[3:6]}.{d[6:9]}-{d[9:]}" if len(d) == 11 else d


def esc(s: str) -> str:
    return (s or "").replace("|", "\\|").strip()


def main() -> None:
    dados = json.loads(OUT_JSON.read_text(encoding="utf-8")) if OUT_JSON.exists() else {}
    todos = []
    seen = set()
    for ln in CPFS_FP.read_text(encoding="utf-8").splitlines():
        d = re.sub(r"\D", "", ln)
        if len(d) == 11 and d not in seen:
            seen.add(d)
            todos.append(d)

    com, arq, sem = [], [], []
    for d in todos:
        r = dados.get(d)
        if not r:
            continue
        st = r.get("status")
        if st == "com_processo":
            com.append((d, r))
        elif st == "arquivado_definitivo":
            arq.append((d, r))
        elif st == "sem_processo":
            sem.append((d, r))
    faltantes = [d for d in todos if d not in dados]

    hoje = date.today().strftime("%d/%m/%Y")
    L = []
    L.append("% Triagem de CPFs — Situação Processual (1º Grau / pje1g)")
    L.append("")
    L.append(f"**Data:** {hoje}  ")
    L.append(f"**Total de CPFs na lista:** {len(todos)}  ")
    L.append(f"**Consultados:** {len(dados)}  ")
    L.append("")
    L.append("## Resumo")
    L.append("")
    L.append("| Grupo | Quantidade |")
    L.append("|---|---:|")
    L.append(f"| Com processo (ativo) | {len(com)} |")
    L.append(f"| Arquivados definitivamente | {len(arq)} |")
    L.append(f"| Sem processo (não ajuizados) | {len(sem)} |")
    if faltantes:
        L.append(f"| Não consultados (reprocessar) | {len(faltantes)} |")
    L.append("")

    def tabela_processos(grupo):
        out = ["| CPF | CNJ | Órgão julgador | Classe | Última movimentação |",
               "|---|---|---|---|---|"]
        for d, r in grupo:
            procs = r.get("processos") or [{}]
            for p in procs:
                out.append(
                    f"| {fmt_cpf(d)} | {esc(p.get('cnj',''))} | {esc(p.get('orgao',''))} "
                    f"| {esc(p.get('classe',''))} | {esc(p.get('ultima_mov',''))} |"
                )
        return out

    L.append("## 1. Com processo (ativo)")
    L.append("")
    L += tabela_processos(com) if com else ["_Nenhum._"]
    L.append("")

    L.append("## 2. Arquivados definitivamente")
    L.append("")
    L += tabela_processos(arq) if arq else ["_Nenhum._"]
    L.append("")

    L.append("## 3. Sem processo (não ajuizados)")
    L.append("")
    if sem:
        L.append("| # | CPF |")
        L.append("|---:|---|")
        for i, (d, _) in enumerate(sem, 1):
            L.append(f"| {i} | {fmt_cpf(d)} |")
    else:
        L.append("_Nenhum._")
    L.append("")

    if faltantes:
        L.append("## 4. Não consultados (falha — reprocessar)")
        L.append("")
        L.append("| # | CPF |")
        L.append("|---:|---|")
        for i, d in enumerate(faltantes, 1):
            L.append(f"| {i} | {fmt_cpf(d)} |")
        L.append("")

    md_fp = REL_DIR / "relatorio_cpfs.md"
    md_fp.write_text("\n".join(L), encoding="utf-8")
    print(f"[rel] markdown: {md_fp}")

    # CSV (uma linha por processo; sem/faltante = 1 linha só com o CPF)
    csv_fp = REL_DIR / "consulta_cpfs.csv"
    with csv_fp.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["cpf", "status", "cnj", "orgao", "classe", "autuado",
                    "polo_ativo", "polo_passivo", "ultima_mov", "arquivado_definitivo"])
        for d in todos:
            r = dados.get(d)
            if not r:
                w.writerow([fmt_cpf(d), "nao_consultado", "", "", "", "", "", "", "", ""])
                continue
            procs = r.get("processos") or []
            if not procs:
                w.writerow([fmt_cpf(d), r.get("status", ""), "", "", "", "", "", "", "", ""])
            for p in procs:
                w.writerow([fmt_cpf(d), r.get("status", ""), p.get("cnj", ""), p.get("orgao", ""),
                            p.get("classe", ""), p.get("autuado", ""), p.get("polo_ativo", ""),
                            p.get("polo_passivo", ""), p.get("ultima_mov", ""),
                            p.get("arquivado_definitivo", False)])
    print(f"[rel] csv: {csv_fp}")

    # pipeline de identidade: pandoc -> brandear_docx
    base_docx = REL_DIR / "_base.docx"
    final_docx = REL_DIR / "Triagem_CPFs_Situacao_Processual.docx"
    subprocess.run(
        ["pandoc", str(md_fp), "-o", str(base_docx), "--toc", "--toc-depth=2",
         "-V", "lang=pt-BR", "--metadata", "title=Triagem de CPFs — Situação Processual"],
        check=True,
    )
    subprocess.run(
        ["python3", str(BASE / "bin" / "brandear_docx.py"),
         str(base_docx), str(final_docx), str(LOGO)],
        check=True,
    )
    base_docx.unlink(missing_ok=True)
    print(f"[rel] DOCX final: {final_docx}")


if __name__ == "__main__":
    main()
