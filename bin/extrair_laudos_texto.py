#!/usr/bin/env python3
"""Extrai o TEXTO COMPLETO dos laudos (todas as páginas) via API do PDF.js do visualizador
do PJe. Saída: mapas/docs_cnj/<cnj>/<id>_FULL.txt + mapas/laudos_texto.json"""
from __future__ import annotations
import argparse, asyncio, json, re, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from bin.coletar_pecas_cnj import abrir
from coletor_pje.varas_1g import pje1g_consulta_context
from coletor_pje.cli import _parse_docs

DOCS = Path("mapas/docs_cnj")
LAUDO_KW = ("laudo pericial", "laudo médico", "laudo medico", "laudo social",
            "estudo social", "avaliação social", "avaliacao social", "socioecon")

JS = """async () => {
  const app = window.PDFViewerApplication;
  if (!app) return null;
  try { await app.pdfLoadingTask.promise; } catch(e) {}
  const doc = app.pdfDocument; if (!doc) return null;
  let out = '';
  for (let i = 1; i <= doc.numPages; i++) {
    const p = await doc.getPage(i);
    const tc = await p.getTextContent();
    out += tc.items.map(t => t.str).join(' ') + '\\n\\n';
  }
  return out;
}"""

async def texto_do_doc(popup, doc_id):
    await popup.evaluate("""(docId) => {
        for (const sp of document.querySelectorAll('span')) {
            if (sp.textContent && sp.textContent.trim().startsWith(docId)) {
                let el = sp.parentElement;
                for (let i=0;i<6&&el;i++){ if(el.tagName==='A'){el.click();return true;} el=el.parentElement; }
            }
        } return false; }""", doc_id)
    await popup.wait_for_timeout(5000)
    for fr in popup.frames:
        try:
            t = await fr.evaluate(JS)
            if t and len(t.strip()) > 300:
                return t
        except Exception:
            continue
    return ""

async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--lista", required=True); ap.add_argument("--sufixo", default="")
    ap.add_argument("--shard", default=""); ap.add_argument("--max-laudos", type=int, default=3)
    a = ap.parse_args()
    cnjs = [l.strip() for l in Path(a.lista).read_text().splitlines() if l.strip()]
    if a.shard:
        I, M = (int(x) for x in a.shard.split("/")); cnjs = [c for k,c in enumerate(cnjs) if k%M==I]
    fp = Path(f"mapas/laudos_texto{a.sufixo}.json")
    res = json.loads(fp.read_text(encoding="utf-8")) if fp.exists() else {}
    print(f"[laudo{a.sufixo}] {len(cnjs)} CNJs, {len(res)} no checkpoint", flush=True)
    async with pje1g_consulta_context(headless=False, sufixo=a.sufixo) as ctx:
        page = ctx.pages[0] if ctx.pages else await ctx.new_page()
        for i, cnj in enumerate(cnjs, 1):
            if cnj in res: continue
            popup = None
            try:
                popup = await abrir(ctx, page, cnj)
                if not popup:
                    res[cnj] = {"ok": False, "erro": "nao_abriu"}; continue
                docs = _parse_docs(await popup.content())
                laudos = [d for d in docs if any(k in (d["tipo"]+" "+d.get("desc","")).lower() for k in LAUDO_KW)]
                laudos = laudos[:a.max_laudos]
                out = DOCS / cnj.replace(".", "_"); out.mkdir(parents=True, exist_ok=True)
                got = []
                for d in laudos:
                    t = await texto_do_doc(popup, d["id"])
                    if t:
                        (out / f"{d['id']}_FULL.txt").write_text(t, encoding="utf-8")
                        got.append({"id": d["id"], "tipo": d["tipo"], "desc": d.get("desc",""),
                                    "chars": len(t), "path": str(out / f"{d['id']}_FULL.txt")})
                res[cnj] = {"ok": True, "laudos": got}
                print(f"[laudo] {i}/{len(cnjs)} {cnj} -> {len(got)} laudos "
                      f"({sum(g['chars'] for g in got)} ch)", flush=True)
            except Exception as e:
                res[cnj] = {"ok": False, "erro": str(e)[:150]}
                print(f"[laudo] {i}/{len(cnjs)} {cnj} ERRO: {e}", flush=True)
            finally:
                try: await popup.close()
                except Exception: pass
                fp.write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"[laudo{a.sufixo}] FIM {len(res)}", flush=True)

asyncio.run(main())
