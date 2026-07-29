"""Pauta de perícia do advogado — dados estruturados sem abrir processo.

A tela /pje/PautaPericia/listView.seam já lista, por perícia designada:
CNJ, classe, especialidade (Médico / Assistente Social), data, hora, valor,
periciado, objeto, motivo, situação, quesitos, órgão julgador e se há laudo.

Especialidade é a resposta direta para "é perícia social ou médica?", que hoje
é inferida por sinônimos no texto do timeline em bin/wf_classificar_cnj.js.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Any

from playwright.async_api import BrowserContext

from .login import PJE_BASE_URL

PAUTA_PERICIA_PATH = "/pje/PautaPericia/listView.seam"
GRID = "table[id*='pautaPericiaAdvogadoGridList']"

# Lê cabeçalho e células por innerText: o HTML dos <th> tem script embutido
# ("Processo function clear_...") que sujaria qualquer parse por regex.
GRID_JS = """() => {
    const tbl = document.querySelector("table[id*='pautaPericiaAdvogadoGridList']");
    if (!tbl) return null;
    const heads = Array.from(tbl.querySelectorAll('thead th'))
        .map(th => (th.innerText || '').trim().split('\\n')[0].trim());
    const rows = Array.from(tbl.querySelectorAll('tbody tr'));
    const out = [];
    for (const tr of rows) {
        const tds = Array.from(tr.querySelectorAll('td')).map(td => (td.innerText || '').trim());
        const o = {};
        heads.forEach((h, i) => { if (h) o[h] = tds[i] === undefined ? '' : tds[i]; });
        if (Object.values(o).some(v => v)) out.push(o);
    }
    return {heads: heads, rows: out};
}"""

CNJ_RE = re.compile(r"\d{7}-\d{2}\.\d{4}\.\d\.\d{2}\.\d{4}")


@dataclass
class Pericia:
    numero: str
    classe: str | None = None
    especialidade: str | None = None  # Médico, Assistente Social, ...
    data: str | None = None  # DD/MM/YYYY
    hora: str | None = None
    realizada_em: str | None = None
    valor: str | None = None
    periciado: str | None = None
    objeto: str | None = None
    motivo: str | None = None
    situacao: str | None = None  # Designada, Cancelada, Realizada
    quesitos: str | None = None
    orgao_julgador: str | None = None
    laudo_anexado: bool = False

    @property
    def social(self) -> bool:
        """Perícia social (assistente social / CRESS), não médica."""
        return "social" in (self.especialidade or "").lower()


def _chave(texto: str) -> str:
    """'Órgão Julgador' -> 'orgao julgador' (sem acento, minúsculo)."""
    t = unicodedata.normalize("NFKD", texto)
    t = "".join(c for c in t if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", t).strip().lower()


# rótulo normalizado da coluna -> campo do dataclass
COLUNAS = {
    "processo": "numero",
    "classe": "classe",
    "especialidade": "especialidade",
    "data e hora da realizacao": "realizada_em",
    "data da pericia": "data",
    "hora da pericia": "hora",
    "valor da pericia": "valor",
    "periciado": "periciado",
    "objeto da pericia": "objeto",
    "motivo": "motivo",
    "situacao": "situacao",
    "quesitos": "quesitos",
    "orgao julgador": "orgao_julgador",
    "laudo anexado": "laudo_anexado",
}


def _para_pericia(linha: dict[str, str]) -> Pericia | None:
    dados: dict[str, Any] = {}
    for rotulo, valor in linha.items():
        campo = COLUNAS.get(_chave(rotulo))
        if not campo:
            continue
        valor = (valor or "").strip()
        if campo == "laudo_anexado":
            dados[campo] = bool(valor)
        elif campo == "numero":
            m = CNJ_RE.search(valor)
            dados[campo] = m.group(0) if m else valor
        else:
            dados[campo] = valor or None
    numero = dados.get("numero")
    if not numero or not CNJ_RE.fullmatch(numero):
        return None
    return Pericia(**dados)


async def listar_pericias(ctx: BrowserContext, debug: bool = False) -> list[Pericia]:
    """Lê a Pauta de perícia. Uma única página — avisa se houver paginação."""
    page = await ctx.new_page()
    try:
        await page.goto(f"{PJE_BASE_URL}{PAUTA_PERICIA_PATH}",
                        wait_until="domcontentloaded", timeout=60_000)
        try:
            await page.wait_for_selector(GRID, timeout=30_000)
        except Exception:
            print("[pautas] grid da pauta de perícia não apareceu (sem perícias designadas?)")
            return []
        await page.wait_for_timeout(2_000)

        bruto = await page.evaluate(GRID_JS)
        if not bruto:
            return []
        if debug:
            print(f"[pautas] colunas: {bruto['heads']}")

        # A grid do PJe pagina com onclick contendo 'page': 'next'; se existir e
        # estiver ativo, o total abaixo está incompleto — melhor avisar do que
        # devolver silenciosamente só a primeira página.
        tem_paginacao = await page.evaluate(
            """() => {
                for (const el of document.querySelectorAll('[onclick]')) {
                    const oc = el.getAttribute('onclick') || '';
                    if (oc.includes("'page': 'next'") || oc.includes('"page":"next"')) {
                        const cls = el.className || '';
                        if (!cls.includes('inact') && !cls.includes('disabled')) return true;
                    }
                }
                return false;
            }"""
        )
        if tem_paginacao:
            print("[pautas] ATENÇÃO: a pauta tem próxima página — total abaixo está INCOMPLETO")

        pericias = [p for p in (_para_pericia(l) for l in bruto["rows"]) if p]
        print(f"[pautas] {len(pericias)} perícia(s) na pauta")
        return pericias
    finally:
        await page.close()
