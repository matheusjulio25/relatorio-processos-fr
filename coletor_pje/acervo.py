"""Listagem do acervo de processos no PJe TRF5.

Estado: lista 876 CNJs com pje_id + pje_ca via paginacao das Caixas de entrada.

PROXIMO PASSO (detalhe do processo):
A URL listProcessoCompletoAdvogado.seam?id=X&ca=Y NAO funciona via navegacao
direta - cai em /pje/error.seam. O link original na listagem e:
  onclick="window.open(URL, 'blank_'); A4J.AJAX.Submit(...)"
O A4J.AJAX.Submit que vem APOS o window.open e o que prepara a sessao no
servidor para a popup. Sem ele, o detalhe falha.

Solucao: ao invs de navegar pra URL salva no manifest, capturar a popup
disparada pelo proprio onclick original durante a varredura do acervo:

    async with page.context.expect_page() as popup_info:
        await page.evaluate("(id) => document.getElementById(id).click()", linha_id)
    popup = await popup_info.value
    await popup.wait_for_load_state("domcontentloaded")
    # ... extrair ultima movimentacao + 3 PDFs (decisao/intimacao/peticao,
    # ignorando certidoes) do HTML da popup.

Ou ainda: substituir o cli.cmd_detalhe pra abrir o painel, expandir caixa
do CNJ alvo, e clicar no link dele com expect_page().
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
# Linha completa de cada processo na listagem. Estrutura visivel (apos tira-tags):
#   ... id=X&ca=Y ... PJEC 0044724-68... NOMEAUT X NOMEREU /30ª Vara Federal PE
#   Distribuído em DD/MM/YYYY Último movimento: DD/MM/YYYY HH:MM - <descricao>. <a class="btn ...
# Capturamos id+ca, CNJ, partes/vara (string solta), data distrib, ultima mov.
# Bloco entre o link e o proximo botao "btn btn-default btn-sm" (proxima acao) tem tudo.
LINHA_RE = re.compile(
    r"listProcessoCompletoAdvogado\.seam\?id=(\d+)&(?:amp;)?ca=([0-9a-f]+)"
    r".{0,5000}?(\d{7}-\d{2}\.\d{4}\.\d\.\d{2}\.\d{4})"
    r"(?P<rest>.{0,3000}?)<a\s",
    re.S,
)
ULT_MOV_RE = re.compile(
    r"[Úu]ltimo movimento:\s*(\d{2}/\d{2}/\d{4}(?:\s+\d{2}:\d{2})?)\s*-\s*([^<\n]+)"
)
DISTRIB_RE = re.compile(r"Distribu[ií]do em\s*(\d{2}/\d{2}/\d{4})")


@dataclass
class ProcessoAcervo:
    numero: str
    classe: str | None = None
    titulo: str | None = None  # partes "AUTOR X REU"
    vara: str | None = None
    distribuido_em: str | None = None  # DD/MM/YYYY
    ultima_movimentacao: str | None = None  # data DD/MM/YYYY HH:MM
    ultima_movimentacao_desc: str | None = None
    pje_id: str | None = None
    pje_ca: str | None = None

    def key(self) -> str:
        return self.numero


def _parse_linha_resto(resto_html: str) -> dict:
    """Extrai partes, vara, distribuicao e ultima mov do bloco apos o CNJ."""
    # remove tags pra ter texto limpo
    txt = re.sub(r"<[^>]+>", " ", resto_html)
    txt = re.sub(r"\s+", " ", txt).strip()
    out: dict = {}

    m = ULT_MOV_RE.search(txt)
    if m:
        out["ultima_movimentacao"] = m.group(1).strip()
        out["ultima_movimentacao_desc"] = m.group(2).strip().rstrip(".")
    m = DISTRIB_RE.search(txt)
    if m:
        out["distribuido_em"] = m.group(1)
    # partes + vara: tudo entre o inicio e "Distribuído em"
    cab = re.split(r"Distribu[ií]do em", txt, maxsplit=1)[0].strip()
    if "/" in cab:
        partes, _, vara = cab.rpartition("/")
        out["titulo"] = partes.strip().rstrip(",")
        out["vara"] = vara.strip()
    elif cab:
        out["titulo"] = cab
    return out


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
        try:
            await page.wait_for_function(
                "() => document.querySelectorAll('#formAbaAcervo\\\\:trAc td.rich-tree-node-icon[rich\\\\:onexpand]').length > 0",
                timeout=60_000,
            )
        except Exception:
            print("[acervo] timeout esperando arvore de cidades; seguindo mesmo assim")
        await page.wait_for_timeout(2_000)

    qtd_cidades = await page.evaluate("""
        () => {
            const tds = document.querySelectorAll('#formAbaAcervo\\\\:trAc td.rich-tree-node-icon');
            let n = 0;
            for (const td of tds) {
                const code = td.getAttribute('rich:onexpand');
                if (!code) continue;
                try { new Function('event', code)(null); n++; } catch (e) {}
            }
            return n;
        }
    """)
    print(f"[acervo] {qtd_cidades} cidades, disparando expand AJAX...")
    try:
        await page.wait_for_function(
            f"() => document.querySelectorAll('a[id$=\":-1::cxItem\"]').length >= {qtd_cidades}",
            timeout=120_000,
        )
    except Exception:
        encontradas = await page.evaluate(
            "() => document.querySelectorAll('a[id$=\":-1::cxItem\"]').length"
        )
        print(f"[acervo] timeout: so {encontradas}/{qtd_cidades} cidades expandiram")
    await page.wait_for_timeout(3_000)

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

        antes_caixa = len(vistos)
        pagina = 1
        while True:
            try:
                html = await page.content()
            except Exception as e:
                print(f"[acervo] page.content falhou: {e}")
                break
            if debug:
                debug_caixas.append((f"{cidade_id}_p{pagina}", html))

            antes_pag = len(vistos)
            for m in LINHA_RE.finditer(html):
                pje_id, pje_ca, numero = m.group(1), m.group(2), m.group(3)
                if numero in vistos:
                    continue
                vistos.add(numero)
                extra = _parse_linha_resto(m.group("rest"))
                yield ProcessoAcervo(
                    numero=numero, pje_id=pje_id, pje_ca=pje_ca, **extra
                )
            novos = len(vistos) - antes_pag

            if novos == 0:
                break
            print(f"[acervo]    pagina {pagina}: +{novos}")

            tem_proxima = await page.evaluate(
                """() => {
                    const all = document.querySelectorAll('[onclick]');
                    for (const el of all) {
                        const oc = el.getAttribute('onclick') || '';
                        if (oc.includes("'page': 'next'") || oc.includes('"page":"next"')) {
                            const cls = el.className || '';
                            if (cls.includes('inact') || cls.includes('disabled')) return false;
                            el.click();
                            return true;
                        }
                    }
                    return false;
                }"""
            )
            if not tem_proxima:
                break
            pagina += 1
            await page.wait_for_timeout(4_000)

        print(f"[acervo] caixa {i+1}/{len(caixa_ids)} ({cidade_id}): +{len(vistos)-antes_caixa} processos em {pagina} pagina(s)")

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
