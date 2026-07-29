#!/usr/bin/env python3
"""Sonda o que Pauta de perícia, Pauta de audiência e a aba Expedientes
entregam sem abrir processo. Salva HTML + PNG em debug/ para calibrar seletores.

Achados da primeira execução (29/07/2026, pje1g TRF5):
  - Pauta de perícia: 15 colunas prontas, já implementado em coletor_pje/pautas.py
  - Pauta de audiência: colunas certas, zero linhas — é formulário de busca
    (processoAudienciaSearchForm) e exige submeter jurisdição/órgão/situações/datas
  - Expedientes: a aba abre, mas exige selecionar uma caixa antes, igual ao
    Acervo; reaproveitar a expansão de árvore de listar_acervo

Uso (da raiz do projeto):  .venv\\Scripts\\python.exe bin\\explorar_pautas.py
"""
from __future__ import annotations

import asyncio
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from coletor_pje.acervo import ACERVO_PATH  # noqa: E402
from coletor_pje.login import PJE_BASE_URL, pje_context  # noqa: E402

DEBUG = Path(__file__).resolve().parent.parent / "debug"

ALVOS = [
    ("pauta_pericia", f"{PJE_BASE_URL}/pje/PautaPericia/listView.seam"),
    ("pauta_audiencia", f"{PJE_BASE_URL}/pje/ProcessoAudiencia/PautaAudiencia/listView.seam"),
]


async def dump(page, nome: str) -> str:
    DEBUG.mkdir(parents=True, exist_ok=True)
    html = await page.content()
    (DEBUG / f"{nome}.html").write_text(html, encoding="utf-8")
    try:
        await page.screenshot(path=str(DEBUG / f"{nome}.png"), full_page=True)
    except Exception:
        pass
    txt = re.sub(r"<script.*?</script>", " ", html, flags=re.S | re.I)
    txt = re.sub(r"<[^>]+>", " ", txt)
    txt = re.sub(r"\s+", " ", txt).strip()
    cnjs = set(re.findall(r"\d{7}-\d{2}\.\d{4}\.\d\.\d{2}\.\d{4}", html))
    datas = set(re.findall(r"\d{2}/\d{2}/\d{4}", txt))
    print(f"  [{nome}] {len(html):>8} bytes | url={page.url[:95]}")
    print(f"  [{nome}] CNJs={len(cnjs)}  datas={len(datas)}")
    print(f"  [{nome}] texto: {txt[:600]}")
    return html


async def main():
    async with pje_context(headless=False) as ctx:
        page = ctx.pages[0] if ctx.pages else await ctx.new_page()

        for nome, url in ALVOS:
            print(f"\n=== {nome} -> {url}")
            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=60_000)
                await page.wait_for_timeout(6_000)
                await dump(page, nome)
            except Exception as e:
                print(f"  [{nome}] ERRO: {e}")

        print("\n=== aba Expedientes")
        try:
            await page.goto(f"{PJE_BASE_URL}{ACERVO_PATH}",
                            wait_until="domcontentloaded", timeout=60_000)
            await page.wait_for_selector("#tabExpedientes_lbl", timeout=30_000)
            await page.locator("#tabExpedientes_lbl").click()
            await page.wait_for_timeout(10_000)
            await dump(page, "expedientes")
        except Exception as e:
            print(f"  [expedientes] ERRO: {e}")


if __name__ == "__main__":
    asyncio.run(main())
