"""CLI do coletor.

Uso:
    python -m coletor_pje.cli listar          # lista todo o acervo
    python -m coletor_pje.cli diff            # mostra só o delta vs manifests/
    python -m coletor_pje.cli diff --apply    # atualiza manifests com o delta
"""
from __future__ import annotations

import argparse
import asyncio
from datetime import datetime, timezone

from .acervo import listar_acervo
from .login import pje_context
from .manifest import Manifest, diff_acervo


async def _coletar(headless: bool, debug: bool = False):
    async with pje_context(headless=headless) as ctx:
        return [p async for p in listar_acervo(ctx, debug=debug)]


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


async def cmd_listar(args):
    processos = await _coletar(headless=args.headless, debug=args.debug)
    for p in processos:
        print(f"{p.numero}\t{p.pje_id or '-'}\t{p.pje_ca or '-'}\t{p.titulo or ''}")
    print(f"\nTotal: {len(processos)}")


async def cmd_diff(args):
    processos = await _coletar(headless=args.headless, debug=args.debug)
    pendentes = diff_acervo(processos)
    print(f"Acervo total: {len(processos)} | Pendentes: {len(pendentes)}")
    for p in pendentes:
        print(f"  + {p.numero}\t{p.ultima_movimentacao or '-'}")
    if args.apply:
        now = _now_iso()
        for p in pendentes:
            m = Manifest.load(p.numero) or Manifest(numero=p.numero)
            m.classe = p.classe
            m.titulo = p.titulo
            m.ultima_movimentacao = p.ultima_movimentacao
            m.pje_id = p.pje_id or m.pje_id
            m.pje_ca = p.pje_ca or m.pje_ca
            m.ultima_coleta = now
            m.save()
        print(f"\n{len(pendentes)} manifests atualizados.")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--headless", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--debug", action="store_true", help="salva screenshot + HTML do painel em debug/")
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("listar")

    p_diff = sub.add_parser("diff")
    p_diff.add_argument("--apply", action="store_true", help="atualiza manifests com o delta")

    args = parser.parse_args()
    coro = {"listar": cmd_listar, "diff": cmd_diff}[args.cmd](args)
    asyncio.run(coro)


if __name__ == "__main__":
    main()
