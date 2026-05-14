"""Listagem do acervo de processos no PJe TRF5.

Os seletores aqui são uma primeira aproximação e provavelmente precisarão de
ajuste após a primeira execução headed contra o ambiente real.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import AsyncIterator

from playwright.async_api import BrowserContext

from .login import PJE_BASE_URL

DEBUG_DIR = Path(os.getenv("DEBUG_DIR", "debug"))

ACERVO_PATH = "/pje/Painel/painel_usuario/advogado.seam"
NUMERO_RE = re.compile(r"\d{7}-\d{2}\.\d{4}\.\d\.\d{2}\.\d{4}")


@dataclass
class ProcessoAcervo:
    numero: str
    classe: str | None
    ultima_movimentacao: str | None  # ISO date string quando possível
    titulo: str | None

    def key(self) -> str:
        return self.numero


def _parse_data(raw: str | None) -> str | None:
    if not raw:
        return None
    raw = raw.strip()
    for fmt in ("%d/%m/%Y %H:%M", "%d/%m/%Y"):
        try:
            return datetime.strptime(raw, fmt).isoformat()
        except ValueError:
            continue
    return raw


async def listar_acervo(ctx: BrowserContext, debug: bool = False) -> AsyncIterator[ProcessoAcervo]:
    """Itera o acervo. Implementação inicial — refinar seletores no ambiente real."""
    page = await ctx.new_page()
    await page.goto(f"{PJE_BASE_URL}{ACERVO_PATH}", wait_until="networkidle")

    if debug:
        DEBUG_DIR.mkdir(parents=True, exist_ok=True)
        await page.screenshot(path=str(DEBUG_DIR / "acervo.png"), full_page=True)
        (DEBUG_DIR / "acervo.html").write_text(await page.content(), encoding="utf-8")
        (DEBUG_DIR / "acervo.url").write_text(page.url, encoding="utf-8")
        print(f"[debug] URL final: {page.url}")
        print(f"[debug] artefatos em {DEBUG_DIR.resolve()}")

    while True:
        linhas = page.locator("table tbody tr")
        total = await linhas.count()
        for i in range(total):
            row = linhas.nth(i)
            texto = (await row.inner_text()).strip()
            m = NUMERO_RE.search(texto)
            if not m:
                continue
            cols = [c.strip() for c in texto.split("\t") if c.strip()]
            yield ProcessoAcervo(
                numero=m.group(0),
                classe=cols[1] if len(cols) > 1 else None,
                ultima_movimentacao=_parse_data(cols[-1] if cols else None),
                titulo=cols[2] if len(cols) > 2 else None,
            )

        proximo = page.get_by_role("link", name=re.compile(r"Pr.xima|>>"))
        if await proximo.count() == 0 or not await proximo.first.is_enabled():
            break
        await proximo.first.click()
        await page.wait_for_load_state("networkidle")

    await page.close()
