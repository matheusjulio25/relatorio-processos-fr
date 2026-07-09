#!/usr/bin/env python3
"""Calibração do modo CNJ: abre cada processo (ConsultaProcesso por número),
lista os documentos (_parse_docs) e baixa o TEXTO de sentença/laudo, para
calibrar a detecção de perícia-resultado e sentença-resultado.

Uso: python3 bin/calibrar_cnj_detalhe.py [arquivo_cnjs]  (default mapas/cnjs_amostra.txt)
"""
from __future__ import annotations
import asyncio
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from coletor_pje.varas_1g import pje1g_consulta_context, PJE1G_BASE_URL  # noqa: E402
from coletor_pje.cli import _parse_docs, _baixar_pecas  # noqa: E402

CONSULTA = f"{PJE1G_BASE_URL}/pje/Processo/ConsultaProcesso/listView.seam"
CNJ_RE = re.compile(r"(\d{7})-?(\d{2})\.?(\d{4})\.?(\d)\.?(\d{2})\.?(\d{4})")
DBG = Path("debug"); DBG.mkdir(exist_ok=True)


async def _fill(page, fid, val):
    sel = "#" + fid.replace(":", "\\:")
    loc = page.locator(sel)
    if await loc.count():
        try:
            await loc.fill(val)
            return True
        except Exception:
            pass
    return False


async def abrir_por_cnj(ctx, page, cnj):
    m = CNJ_RE.search(cnj)
    seq, dv, ano, ramo, trib, org = m.groups()
    await page.goto(CONSULTA, wait_until="domcontentloaded", timeout=60_000)
    await page.wait_for_timeout(1_500)
    await _fill(page, "fPP:numeroProcesso:numeroSequencial", seq)
    await _fill(page, "fPP:numeroProcesso:numeroDigitoVerificador", dv)
    await _fill(page, "fPP:numeroProcesso:Ano", ano)
    await _fill(page, "fPP:numeroProcesso:ramoJustica", ramo)
    await _fill(page, "fPP:numeroProcesso:respectivoTribunal", trib)
    await _fill(page, "fPP:numeroProcesso:NumeroOrgaoJustica", org)

    def is_post(r):
        try:
            return "listView.seam" in r.url and r.request.method == "POST"
        except Exception:
            return False
    try:
        async with page.expect_response(is_post, timeout=30_000):
            await page.locator("#fPP\\:searchProcessos").click()
    except Exception:
        pass
    await page.wait_for_timeout(2_500)
    # abre a popup do processo
    try:
        async with ctx.expect_page(timeout=25_000) as pinfo:
            await page.evaluate(
                """() => {
                    const CNJ=/\\d{7}-\\d{2}\\.\\d{4}\\.\\d\\.\\d{2}\\.\\d{4}/;
                    for (const a of document.querySelectorAll('a[onclick*="idProcessoSelecionado"]')) {
                        const t=(a.textContent||'')+(a.getAttribute('title')||'');
                        if (CNJ.test(t)) { a.click(); return true; }
                    }
                    const a=document.querySelector('a[onclick*="idProcessoSelecionado"]');
                    if(a){a.click(); return true;}
                    return false;
                }"""
            )
        popup = await pinfo.value
        await popup.wait_for_load_state("domcontentloaded", timeout=60_000)
        await popup.wait_for_timeout(5_000)
        return popup
    except Exception as e:
        print(f"    [abrir] falhou: {e}")
        return None


async def main():
    arq = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("mapas/cnjs_amostra.txt")
    cnjs = [l.strip() for l in arq.read_text(encoding="utf-8").splitlines() if l.strip()]
    resumo = {}
    async with pje1g_consulta_context(headless=False) as ctx:
        page = ctx.pages[0] if ctx.pages else await ctx.new_page()
        for cnj in cnjs:
            print(f"\n=== {cnj} ===", flush=True)
            popup = await abrir_por_cnj(ctx, page, cnj)
            if not popup:
                resumo[cnj] = {"erro": "nao_abriu"}
                continue
            html = await popup.content()
            (DBG / f"detalhe_{cnj.replace('.','_')}.html").write_text(html, encoding="utf-8")
            docs = _parse_docs(html)
            tipos = [d["tipo"] for d in docs]
            print(f"    {len(docs)} docs. tipos: {sorted(set(tipos))}", flush=True)
            sent = [d for d in docs if "senten" in d["tipo"].lower()]
            laudos = [d for d in docs if "laudo" in d["tipo"].lower()]
            print(f"    sentenças={len(sent)} laudos={len(laudos)}", flush=True)
            out = DBG / f"doctext_{cnj.replace('.','_')}"
            out.mkdir(exist_ok=True)
            textos = await _baixar_pecas(popup, (sent[:1] + laudos[:2]), out, log_prefix="    ")
            for t in textos:
                print(f"    -> {t['tipo']} [{t['ext']}] {len(t.get('texto',''))} chars", flush=True)
            resumo[cnj] = {"n_docs": len(docs), "tipos": sorted(set(tipos)),
                           "sentencas": len(sent), "laudos": len(laudos),
                           "textos": [{"tipo": t["tipo"], "chars": len(t.get("texto", "")),
                                       "amostra": (t.get("texto", "") or "")[:400]} for t in textos]}
            try:
                await popup.close()
            except Exception:
                pass
    Path("debug/calibra_resumo.json").write_text(json.dumps(resumo, ensure_ascii=False, indent=1), encoding="utf-8")
    print("\n[fim] resumo em debug/calibra_resumo.json")


if __name__ == "__main__":
    asyncio.run(main())
