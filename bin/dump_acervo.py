#!/usr/bin/env python3
"""Dump da lista COMPLETA do acervo (sem abrir processo) -> mapas/acervo_atual.json."""
from __future__ import annotations
import asyncio, json, sys
from datetime import datetime
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from coletor_pje.login import PJE_BASE_URL
from coletor_pje.varas_1g import pje1g_consulta_context
from coletor_pje.acervo import listar_acervo, ACERVO_PATH
OUT = Path("mapas/acervo_atual.json")

async def main():
    procs = []
    async with pje1g_consulta_context(headless=False) as ctx:
        page = ctx.pages[0] if ctx.pages else await ctx.new_page()
        ok = False
        for tent in range(48):
            try:
                await page.goto(f"{PJE_BASE_URL}{ACERVO_PATH}", wait_until="domcontentloaded", timeout=30_000)
            except Exception:
                pass
            await page.wait_for_timeout(2500)
            if await page.locator("#tabAcervo_lbl").count() > 0:
                ok = True; break
            await page.wait_for_timeout(5000)
        if not ok:
            print("[dump] painel não subiu"); return
        print("[dump] sessão OK, varrendo...", flush=True)
        async for p in listar_acervo(ctx):
            procs.append({"cnj": p.numero, "vara": p.vara, "partes": p.titulo,
                          "ultimo_mov": p.ultima_movimentacao,
                          "ultimo_mov_desc": p.ultima_movimentacao_desc})
    OUT.write_text(json.dumps({"gerado_em": datetime.now().strftime("%Y-%m-%d %H:%M"),
                               "total": len(procs), "processos": procs},
                              ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"[dump] {len(procs)} processos -> {OUT}")

asyncio.run(main())
