#!/usr/bin/env python3
"""Fase 2a — enriquecimento por CNJ: abre cada processo (ConsultaProcesso por
número), marca TEM SENTENÇA e classifica o RESULTADO da sentença (do texto HTML).
Registra os laudos (ids/tipos) para a fase 2b (visão/OCR dos PDFs).

Resume-safe: mapas/enriquecimento_cnj.json. Uso: python3 bin/enriquecer_cnj.py [--limit N]
"""
from __future__ import annotations
import argparse
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
POR = Path("mapas/pericias_por_processo.json")
OUT = Path("mapas/enriquecimento_cnj.json")
LAUDO_DIR = Path("mapas/laudos_pdf")


def classificar_sentenca(txt: str) -> str:
    """Classifica o dispositivo. Cobre a redação real do 1º grau (ACOLHO/REJEITO/
    condenar o INSS), não só 'julgo procedente/improcedente'."""
    t = re.sub(r"\s+", " ", txt or "").lower()
    # foca no dispositivo (após marcadores), senão usa o texto todo
    for marca in ("dispositivo", "ante o exposto", "isso posto", "isto posto",
                  "diante do exposto", "em face disso", "posto isso"):
        k = t.rfind(marca)
        if k >= 0:
            t = t[k:]
            break
    parcial = ("parcialmente proceden" in t or "acolho em parte" in t
               or "acolho parcialmente" in t or "procedência parcial" in t
               or "julgo parcialmente" in t)
    favoravel = (re.search(r"julgo\s+proceden", t) or re.search(r"\bacolho\b", t)
                 or "condenar o inss" in t or "condeno o inss" in t
                 or "concedo o benef" in t or "defiro o benef" in t
                 or "determino a implanta" in t or "restabele" in t)
    desfav = (re.search(r"julgo\s+improceden", t) or re.search(r"\brejeito\b", t)
              or "nego provimento" in t or "indefiro o pedido" in t
              or "improcedente" in t)
    extincao = ("sem resolução de mérito" in t or "sem resolucao de merito" in t
                or re.search(r"\bhomologo\b", t))
    if parcial and favoravel:
        return "Parcialmente procedente (favorável)"
    if favoravel and not desfav:
        return "Procedente (favorável)"
    if desfav and not favoravel:
        return "Improcedente (desfavorável)"
    if favoravel and desfav:
        return "Parcialmente procedente (favorável)"  # acolheu parte, rejeitou parte
    if extincao:
        return "Extinção sem mérito (revisar)"
    return "Indeterminado (revisar)"


async def _fill(page, fid, val):
    loc = page.locator("#" + fid.replace(":", "\\:"))
    if await loc.count():
        try:
            await loc.fill(val)
        except Exception:
            pass


async def abrir_por_cnj(ctx, page, cnj, tentativas=2):
    m = CNJ_RE.search(cnj)
    seq, dv, ano, ramo, trib, org = m.groups()
    for _ in range(tentativas):
        await page.goto(CONSULTA, wait_until="domcontentloaded", timeout=60_000)
        await page.wait_for_timeout(1_200)
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
        await page.wait_for_timeout(2_000)
        try:
            async with ctx.expect_page(timeout=20_000) as pinfo:
                await page.evaluate(
                    """() => {
                        const CNJ=/\\d{7}-\\d{2}\\.\\d{4}\\.\\d\\.\\d{2}\\.\\d{4}/;
                        for (const a of document.querySelectorAll('a[onclick*="idProcessoSelecionado"]')) {
                            const t=(a.textContent||'')+(a.getAttribute('title')||'');
                            if (CNJ.test(t)) { a.click(); return true; }
                        }
                        const a=document.querySelector('a[onclick*="idProcessoSelecionado"]');
                        if(a){a.click(); return true;} return false;
                    }"""
                )
            popup = await pinfo.value
            await popup.wait_for_load_state("domcontentloaded", timeout=60_000)
            await popup.wait_for_timeout(4_500)
            return popup
        except Exception:
            continue
    return None


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()

    cnjs = list(json.loads(POR.read_text(encoding="utf-8")).keys())
    if args.limit:
        cnjs = cnjs[: args.limit]
    res = json.loads(OUT.read_text(encoding="utf-8")) if OUT.exists() else {}
    LAUDO_DIR.mkdir(parents=True, exist_ok=True)
    total = len(cnjs)
    print(f"[enr] {total} CNJs; {len(res)} no checkpoint", flush=True)

    async with pje1g_consulta_context(headless=False) as ctx:
        page = ctx.pages[0] if ctx.pages else await ctx.new_page()
        for i, cnj in enumerate(cnjs, 1):
            if cnj in res:
                continue
            popup = await abrir_por_cnj(ctx, page, cnj)
            if not popup:
                print(f"[enr] {i}/{total} {cnj} -> NAO ABRIU", flush=True)
                res[cnj] = {"aberto": False, "tem_sentenca": None,
                            "resultado_sentenca": "—", "laudo_docs": []}
                OUT.write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
                continue
            try:
                html = await popup.content()
                docs = _parse_docs(html)
                sents = [d for d in docs if "senten" in d["tipo"].lower()]
                laudos = [{"id": d["id"], "tipo": d["tipo"], "desc": d["desc"]}
                          for d in docs if "laudo" in d["tipo"].lower()]
                resultado = "—"
                if sents:
                    baixados = await _baixar_pecas(popup, sents[:2], LAUDO_DIR, log_prefix="   ")
                    melhor = max(baixados, key=lambda x: len(x.get("texto", "")), default=None)
                    if melhor and melhor.get("texto"):
                        resultado = classificar_sentenca(melhor["texto"])
                    else:
                        resultado = "Sentença sem texto (revisar)"
                res[cnj] = {"aberto": True, "tem_sentenca": bool(sents),
                            "resultado_sentenca": resultado, "n_laudos": len(laudos),
                            "laudo_docs": laudos}
                print(f"[enr] {i}/{total} {cnj} -> sentença={bool(sents)} | {resultado} | laudos={len(laudos)}", flush=True)
            except Exception as e:
                print(f"[enr] {i}/{total} {cnj} ERRO: {e}", flush=True)
                res[cnj] = {"aberto": True, "erro": str(e), "tem_sentenca": None,
                            "resultado_sentenca": "erro", "laudo_docs": []}
            finally:
                try:
                    await popup.close()
                except Exception:
                    pass
            OUT.write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")

    from collections import Counter
    c = Counter(v.get("resultado_sentenca", "—") for v in res.values())
    print(f"[enr] FIM. {dict(c)}", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
