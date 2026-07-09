#!/usr/bin/env python3
"""Planilha de Maturidade para Julgamento — Controladoria.

Consolida a pauta de perícia (PDF) por processo e, quando disponível, o
enriquecimento do PJe (sentença + resultado do laudo). Gera .xlsx organizado
por colunas, com abas Resumo / Processos / Perícias (detalhe).

Entradas:
  mapas/pericias_pauta.json        (uma linha por perícia — do PDF)
  mapas/enriquecimento_cnj.json    (opcional: {cnj: {tem_sentenca, resultado_sentenca,
                                     resultado_laudo, ultima_mov}})
Saída: relatorios/Maturidade_Julgamento.xlsx  (+ cópia no Drive Controladoria)
"""
from __future__ import annotations

import json
import re
import shutil
from collections import defaultdict
from datetime import date
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

BASE = Path(__file__).resolve().parent.parent
PAUTA = BASE / "mapas" / "pericias_pauta.json"
ENRIQ = BASE / "mapas" / "enriquecimento_cnj.json"
OUT = BASE / "relatorios" / "Maturidade_Julgamento.xlsx"
DRIVE = Path("/Users/matheusjuliorego/Library/CloudStorage/"
             "GoogleDrive-matheus@julioregoadv.com/Drives compartilhados/"
             "Controladoria - Planilhas de Controle")

MARCA = "7F8187"       # cinza-taupe da marca
VERDE = "C6EFCE"
AMARELO = "FFEB9C"
VERMELHO = "FFC7CE"
CINZA = "E7E6E6"

FEITA = {"realizada", "enviadoparapagamento", "aguardandosolicitacaopagamentonoajg"}


def nsit(s):
    return re.sub(r"\s+", "", (s or "").lower())


def is_social(esp):
    return "social" in (esp or "").lower()


def consolidar():
    rows = json.loads(PAUTA.read_text(encoding="utf-8"))
    enr = json.loads(ENRIQ.read_text(encoding="utf-8")) if ENRIQ.exists() else {}
    por = defaultdict(lambda: {
        "cliente": "", "orgao": "", "classe": "", "peritos": set(),
        "espec": set(), "situacoes": [], "medica": 0, "social": 0, "feitas": 0,
        "datas": [],
    })
    for r in rows:
        c = por[r["cnj"]]
        c["cliente"] = c["cliente"] or r.get("periciado", "")
        c["orgao"] = c["orgao"] or r.get("orgao", "")
        c["classe"] = c["classe"] or r.get("classe", "")
        if r.get("perito"):
            c["peritos"].add(r["perito"])
        if r.get("espec"):
            c["espec"].add(r["espec"])
        c["situacoes"].append(r.get("situacao", ""))
        if r.get("data"):
            c["datas"].append(r["data"])
        if nsit(r.get("situacao", "")) in FEITA:
            c["feitas"] += 1
            if is_social(r.get("espec", "")):
                c["social"] += 1
            else:
                c["medica"] += 1
    saida = []
    for cnj, c in por.items():
        e = enr.get(cnj, {})
        tem_sent = e.get("tem_sentenca")
        # maturidade (perícia): sinal principal p/ despacho
        if c["feitas"] >= 2:
            mat = "MADURO — 2+ perícias feitas"
        elif c["feitas"] == 1:
            mat = "1 perícia feita"
        else:
            mat = "Sem perícia realizada"
        # ação sugerida combinando perícia + sentença (quando houver enriquecimento)
        if tem_sent is True:
            acao = "Já sentenciado — conferir resultado/recurso"
        elif c["feitas"] >= 2:
            acao = "DESPACHAR — maduro p/ julgamento"
        elif c["feitas"] == 1:
            acao = "Verificar necessidade de 2ª perícia (BPC: médica+social)"
        else:
            acao = "Aguardar/cobrar realização da perícia"
        saida.append({
            "cnj": cnj, "cliente": c["cliente"], "orgao": c["orgao"], "classe": c["classe"],
            "medica_feita": "Sim" if c["medica"] else "Não",
            "social_feita": "Sim" if c["social"] else "Não",
            "n_pericias_feitas": c["feitas"],
            "especialidades": ", ".join(sorted(c["espec"])),
            "peritos": " | ".join(sorted(c["peritos"])),
            "situacoes": ", ".join(sorted(set(c["situacoes"]))),
            "maturidade_pericia": mat,
            "tem_sentenca": ("Sim" if tem_sent is True else "Não" if tem_sent is False else "—"),
            "resultado_sentenca": e.get("resultado_sentenca", "—"),
            "resultado_laudo": e.get("resultado_laudo", "—"),
            "ultima_mov": e.get("ultima_mov", "—"),
            "acao": acao,
        })
    # ordena: maduros (2+) primeiro, depois 1 perícia, depois resto
    saida.sort(key=lambda x: (-x["n_pericias_feitas"], x["cliente"]))
    return saida, rows


COLS = [
    ("cnj", "Processo (CNJ)", 22),
    ("cliente", "Cliente (periciado)", 26),
    ("orgao", "Órgão julgador", 16),
    ("classe", "Classe", 20),
    ("medica_feita", "Perícia médica", 12),
    ("social_feita", "Perícia social", 12),
    ("n_pericias_feitas", "Nº perícias feitas", 10),
    ("especialidades", "Especialidades", 22),
    ("peritos", "Perito(s)", 26),
    ("situacoes", "Situações", 22),
    ("maturidade_pericia", "Maturidade (perícia)", 24),
    ("tem_sentenca", "Tem sentença?", 12),
    ("resultado_sentenca", "Resultado sentença", 18),
    ("resultado_laudo", "Resultado laudo", 18),
    ("ultima_mov", "Última movimentação", 30),
    ("acao", "Ação sugerida", 34),
]


def estilizar_header(ws, ncols):
    fill = PatternFill("solid", fgColor=MARCA)
    for j in range(1, ncols + 1):
        cel = ws.cell(row=1, column=j)
        cel.fill = fill
        cel.font = Font(bold=True, color="FFFFFF", name="Segoe UI", size=10)
        cel.alignment = Alignment(vertical="center", horizontal="center", wrap_text=True)
    ws.freeze_panes = "A2"
    ws.row_dimensions[1].height = 30


def main():
    saida, rows = consolidar()
    wb = Workbook()

    # ---- Aba Resumo ----
    ws = wb.active
    ws.title = "Resumo"
    hoje = date.today().strftime("%d/%m/%Y")
    n2 = sum(1 for s in saida if s["n_pericias_feitas"] >= 2)
    n1 = sum(1 for s in saida if s["n_pericias_feitas"] == 1)
    n0 = sum(1 for s in saida if s["n_pericias_feitas"] == 0)
    linhas_resumo = [
        ["Maturidade para Julgamento — Controladoria (Fernandes & Rêgo)", ""],
        ["Gerado em", hoje],
        ["Fonte", "Pauta de perícia (PJe TRF5 1º grau) + enriquecimento PJe"],
        ["", ""],
        ["Processos únicos", len(saida)],
        ["Perícias (linhas na pauta)", len(rows)],
        ["MADURO — 2+ perícias feitas", n2],
        ["1 perícia feita", n1],
        ["Sem perícia realizada", n0],
    ]
    for i, (a, b) in enumerate(linhas_resumo, 1):
        ws.cell(row=i, column=1, value=a).font = Font(bold=(i == 1), name="Segoe UI",
                                                       size=12 if i == 1 else 10)
        ws.cell(row=i, column=2, value=b).font = Font(name="Segoe UI", size=10)
    ws.column_dimensions["A"].width = 42
    ws.column_dimensions["B"].width = 22

    # ---- 3 abas SEPARADAS por prioridade (atitudes diferentes) ----
    blocos = [
        ("1. Maduros (2+ perícias)",
         lambda s: s["n_pericias_feitas"] >= 2,
         "PRIORIDADE 1 — DESPACHAR p/ julgamento (perícias médica + social realizadas)",
         VERDE),
        ("2. Uma perícia",
         lambda s: s["n_pericias_feitas"] == 1,
         "PRIORIDADE 2 — VERIFICAR 2ª perícia (BPC exige médica + social) ou aguardar laudo/sentença",
         AMARELO),
        ("3. Sem perícia realizada",
         lambda s: s["n_pericias_feitas"] == 0,
         "PRIORIDADE 3 — COBRAR realização da perícia (agendada/cancelada/ausência)",
         CINZA),
    ]
    for nome, filtro, titulo_acao, cor in blocos:
        linhas = [s for s in saida if filtro(s)]
        ws2 = wb.create_sheet(nome)
        # linha 1: título/atitude do bloco (mesclada)
        ws2.merge_cells(start_row=1, start_column=1, end_row=1, end_column=len(COLS))
        t = ws2.cell(row=1, column=1, value=f"{titulo_acao}   —   {len(linhas)} processos")
        t.fill = PatternFill("solid", fgColor=cor)
        t.font = Font(bold=True, name="Segoe UI", size=11, color="333333")
        t.alignment = Alignment(vertical="center", horizontal="left")
        ws2.row_dimensions[1].height = 26
        # linha 2: cabeçalho
        for j, (_, titulo, w) in enumerate(COLS, 1):
            ws2.cell(row=2, column=j, value=titulo)
            ws2.column_dimensions[get_column_letter(j)].width = w
        fill_h = PatternFill("solid", fgColor=MARCA)
        for j in range(1, len(COLS) + 1):
            cel = ws2.cell(row=2, column=j)
            cel.fill = fill_h
            cel.font = Font(bold=True, color="FFFFFF", name="Segoe UI", size=10)
            cel.alignment = Alignment(vertical="center", horizontal="center", wrap_text=True)
        ws2.row_dimensions[2].height = 30
        ws2.freeze_panes = "A3"
        for i, s in enumerate(linhas, 3):
            for j, (key, _, _) in enumerate(COLS, 1):
                c = ws2.cell(row=i, column=j, value=s[key])
                c.font = Font(name="Segoe UI", size=10)
                c.alignment = Alignment(vertical="center", wrap_text=(key in ("acao", "ultima_mov", "peritos")))
        if linhas:
            ws2.auto_filter.ref = f"A2:{get_column_letter(len(COLS))}{len(linhas)+2}"

    # ---- Aba Perícias (detalhe) ----
    wd = wb.create_sheet("Perícias (detalhe)")
    det_cols = [("cnj", "Processo", 22), ("periciado", "Periciado", 26), ("espec", "Especialidade", 16),
                ("perito", "Perito", 28), ("data", "Data perícia", 12), ("situacao", "Situação", 18),
                ("orgao", "Órgão", 16), ("classe", "Classe", 22)]
    for j, (_, t, w) in enumerate(det_cols, 1):
        wd.cell(row=1, column=j, value=t)
        wd.column_dimensions[get_column_letter(j)].width = w
    estilizar_header(wd, len(det_cols))
    for i, r in enumerate(rows, 2):
        for j, (key, _, _) in enumerate(det_cols, 1):
            wd.cell(row=i, column=j, value=r.get(key, "")).font = Font(name="Segoe UI", size=10)
    wd.auto_filter.ref = f"A1:{get_column_letter(len(det_cols))}{len(rows)+1}"

    OUT.parent.mkdir(exist_ok=True)
    wb.save(OUT)
    print(f"[xlsx] salvo: {OUT}")

    # cópia no Drive Controladoria
    if DRIVE.exists():
        dest = DRIVE / OUT.name
        shutil.copy2(OUT, dest)
        print(f"[drive] copiado: {dest}")
    else:
        print(f"[drive] AVISO: pasta não encontrada: {DRIVE}")


if __name__ == "__main__":
    main()
