#!/usr/bin/env python3
"""Baixa TODOS os PDFs candidatos a laudo do perito (rede ampla) e marca qual contem
o nome do perito da aba de pericias. Saida: mapas/laudos_pdf2/ + mapas/laudos_pdf2.json"""
from __future__ import annotations
import argparse, asyncio, base64, json, re, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from bin.coletar_pecas_cnj import abrir
from coletor_pje.varas_1g import pje1g_consulta_context
from coletor_pje.cli import _parse_docs

OUT = Path("mapas/laudos_pdf2"); OUT.mkdir(parents=True, exist_ok=True)
CAND = re.compile(r"laudo|per[íi]cia|social|socioecon|parecer", re.I)

JS = """async () => {
  const app = window.PDFViewerApplication; if (!app) return null;
  try { await app.pdfLoadingTask.promise; } catch(e) {}
  const doc = app.pdfDocument; if (!doc) return null;
  const data = await doc.getData();
  let s=''; const CH=0x8000;
  for (let i=0;i<data.length;i+=CH) s += String.fromCharCode.apply(null, data.subarray(i,i+CH));
  return { b64: btoa(s), pages: doc.numPages };
}"""

async def pega(popup, doc_id):
    await popup.evaluate("""(docId)=>{
        for (const sp of document.querySelectorAll('span')) {
            if (sp.textContent && sp.textContent.trim().startsWith(docId)) {
                let el=sp.parentElement;
                for (let i=0;i<6&&el;i++){ if(el.tagName==='A'){el.click();return true;} el=el.parentElement; }
            }
        } return false; }""", doc_id)
    await popup.wait_for_timeout(4500)
    for fr in popup.frames:
        try:
            r = await fr.evaluate(JS)
            if r and r.get("b64"): return r
        except Exception:
            continue
    return None

async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--lista", required=True); ap.add_argument("--sufixo", default="")
    ap.add_argument("--shard", default=""); ap.add_argument("--max", type=int, default=8)
    a = ap.parse_args()
    cnjs = [l.strip() for l in Path(a.lista).read_text().splitlines() if l.strip()]
    if a.shard:
        I,M = (int(x) for x in a.shard.split("/")); cnjs=[c for k,c in enumerate(cnjs) if k%M==I]
    fp = Path(f"mapas/laudos_pdf2{a.sufixo}.json")
    res = json.loads(fp.read_text(encoding="utf-8")) if fp.exists() else {}
    print(f"[amplo{a.sufixo}] {len(cnjs)} CNJs, {len(res)} no checkpoint", flush=True)
    async with pje1g_consulta_context(headless=False, sufixo=a.sufixo) as ctx:
        page = ctx.pages[0] if ctx.pages else await ctx.new_page()
        for i, cnj in enumerate(cnjs, 1):
            if cnj in res: continue
            popup = None
            try:
                popup = await abrir(ctx, page, cnj)
                if not popup: res[cnj]={"ok":False,"erro":"nao_abriu"}; continue
                docs = _parse_docs(await popup.content())
                # candidatos: qualquer doc de laudo/pericia + os 2 seguintes de cada
                idx=[k for k,d in enumerate(docs) if CAND.search(d["tipo"]+" "+d.get("desc",""))]
                sel,vis=[],set()
                for k in idx:
                    for j in range(k, min(len(docs), k+3)):
                        if docs[j]["id"] in vis: continue
                        vis.add(docs[j]["id"]); sel.append(docs[j])
                got=[]
                for d in sel[:a.max]:
                    r = await pega(popup, d["id"])
                    if not r: continue
                    f = OUT / f"{cnj.replace('.','_')}__{d['id']}.pdf"
                    f.write_bytes(base64.b64decode(r["b64"]))
                    got.append({"id":d["id"],"tipo":d["tipo"],"desc":d.get("desc",""),
                                "pdf":str(f),"pages":r["pages"],"bytes":f.stat().st_size})
                res[cnj]={"ok":True,"docs":[{"id":d["id"],"tipo":d["tipo"],"desc":d.get("desc","")} for d in docs],
                          "baixados":got}
                print(f"[amplo] {i}/{len(cnjs)} {cnj} -> {len(got)} pdf(s) de {len(sel)} candidatos", flush=True)
            except Exception as e:
                res[cnj]={"ok":False,"erro":str(e)[:150]}
                print(f"[amplo] {i}/{len(cnjs)} {cnj} ERRO: {e}", flush=True)
            finally:
                try: await popup.close()
                except Exception: pass
                fp.write_text(json.dumps(res,ensure_ascii=False,indent=1),encoding="utf-8")
    print(f"[amplo{a.sufixo}] FIM {len(res)}", flush=True)

asyncio.run(main())
