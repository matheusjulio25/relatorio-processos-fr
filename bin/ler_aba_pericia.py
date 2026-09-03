#!/usr/bin/env python3
"""Abre cada processo e le a ABA DE PERICIAS (marcaPericia) -> mapas/aba_pericia.json.
Diz, por processo, se ha pericia designada/realizada, com data, perito e situacao."""
from __future__ import annotations
import argparse, asyncio, json, re, sys
from pathlib import Path
from bs4 import BeautifulSoup
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from bin.coletar_pecas_cnj import abrir
from coletor_pje.varas_1g import pje1g_consulta_context

DT=re.compile(r'(\d{2}/\d{2}/\d{4})')

async def ler_pericias(pop):
    try:
        await pop.evaluate("""()=>{
            const c=[...document.querySelectorAll('a,span,div,td')];
            const el=c.find(e=>/per[ií]cia/i.test((e.textContent||'').trim()) && (e.onclick||e.getAttribute('onclick')||e.href));
            if(el){el.click(); return true} return false;}""")
        await pop.wait_for_timeout(3000)
    except Exception:
        pass
    s=BeautifulSoup(await pop.content(),"lxml")
    tb=s.find(id=lambda x: x and "processoPericiaNovaPericiaList" in x and x.endswith(":tb"))
    out=[]
    for r in (tb.find_all("tr", class_=re.compile("rich-table-row")) if tb else []):
        cels=[re.sub(r"\s+"," ",td.get_text(" ",strip=True)) for td in r.find_all("td")]
        if not cels or not any(cels): continue
        m=DT.search(" ".join(cels))
        out.append({"data":m.group(1) if m else "",
                    "periciado":cels[1] if len(cels)>1 else "",
                    "perito":cels[3] if len(cels)>3 else "",
                    "situacao":cels[-1] if cels else "",
                    "cels":cels})
    return out

async def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--lista",required=True); ap.add_argument("--sufixo",default="")
    ap.add_argument("--shard",default="")
    a=ap.parse_args()
    cnjs=[l.strip() for l in Path(a.lista).read_text().splitlines() if l.strip()]
    if a.shard:
        I,M=(int(x) for x in a.shard.split("/")); cnjs=[c for k,c in enumerate(cnjs) if k%M==I]
    fp=Path(f"mapas/aba_pericia{a.sufixo}.json")
    res=json.loads(fp.read_text(encoding="utf-8")) if fp.exists() else {}
    print(f"[per{a.sufixo}] {len(cnjs)} CNJs, {len(res)} no checkpoint",flush=True)
    async with pje1g_consulta_context(headless=False, sufixo=a.sufixo) as ctx:
        page=ctx.pages[0] if ctx.pages else await ctx.new_page()
        for i,cnj in enumerate(cnjs,1):
            if cnj in res: continue
            pop=None
            try:
                pop=await abrir(ctx,page,cnj)
                if not pop:
                    res[cnj]={"ok":False,"erro":"nao_abriu"}; continue
                pers=await ler_pericias(pop)
                res[cnj]={"ok":True,"pericias":pers,"n":len(pers)}
                sit=", ".join(sorted({p["situacao"][:28] for p in pers})) or "NENHUMA"
                print(f"[per] {i}/{len(cnjs)} {cnj} -> {len(pers)} perícia(s) [{sit}]",flush=True)
            except Exception as e:
                res[cnj]={"ok":False,"erro":str(e)[:150]}
                print(f"[per] {i}/{len(cnjs)} {cnj} ERRO: {e}",flush=True)
            finally:
                try: await pop.close()
                except Exception: pass
                fp.write_text(json.dumps(res,ensure_ascii=False,indent=1),encoding="utf-8")
    print(f"[per{a.sufixo}] FIM {len(res)}",flush=True)

asyncio.run(main())
