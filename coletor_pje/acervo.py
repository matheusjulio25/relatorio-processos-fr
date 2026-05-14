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
    await page.goto(f"{PJE_BASE_URL}{ACERVO_PATH}", wait_until="domcontentloaded", timeout=60_000)
    await page.wait_for_selector("#tabAcervo_lbl", timeout=30_000)

    aba = page.locator("#tabAcervo_lbl")
    if await aba.count() > 0:
        await aba.click()
        await page.wait_for_timeout(10_000)

    html_inicial = await page.content()
    caixa_ids = re.findall(r'id="(formAbaAcervo:trAc:\d+:-1::cxItem)"', html_inicial)
    print(f"[acervo] {len(caixa_ids)} caixas de entrada encontradas")

    vistos: set[str] = set()
    debug_caixas = []
    for i, cidade_id in enumerate(caixa_ids):
        print(f"[acervo] -> caixa {i+1}/{len(caixa_ids)} {cidade_id}")
        try:
            ok = await page.evaluate(
                "(id) => { const e = document.getElementById(id); if (!e) return 'no-elem'; try { e.onclick(); return 'ok'; } catch (err) { return 'err:' + err.message; } }",
                cidade_id,
            )
            print(f"[acervo]    evaluate -> {ok}")
            await page.wait_for_timeout(5_000)
        except Exception as e:
            print(f"[acervo] erro clicando caixa {cidade_id}: {e}")
            continue

        try:
            html = await page.content()
        except Exception as e:
            print(f"[acervo] page.content falhou: {e}")
            break
        if debug:
            debug_caixas.append((cidade_id, html))

        antes = len(vistos)
        for numero in NUMERO_RE.findall(html):
            if numero == "9999999-99.9999.9.99.9999" or numero in vistos:
                continue
            vistos.add(numero)
            yield ProcessoAcervo(numero=numero, classe=None, ultima_movimentacao=None, titulo=None)
        print(f"[acervo] caixa {i+1}/{len(caixa_ids)} ({cidade_id}): +{len(vistos)-antes} processos")

    if debug:
        DEBUG_DIR.mkdir(parents=True, exist_ok=True)
        await page.screenshot(path=str(DEBUG_DIR / "acervo.png"), full_page=True)
        (DEBUG_DIR / "acervo.html").write_text(await page.content(), encoding="utf-8")
        (DEBUG_DIR / "acervo.url").write_text(page.url, encoding="utf-8")
        for cid, html in debug_caixas:
            safe = cid.replace(":", "_")
            (DEBUG_DIR / f"caixa_{safe}.html").write_text(html, encoding="utf-8")
        print(f"[debug] artefatos em {DEBUG_DIR.resolve()}")

    await page.close()
