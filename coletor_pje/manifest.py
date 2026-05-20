"""Manifests por processo — fonte da verdade do que já foi coletado/analisado."""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

from .acervo import ProcessoAcervo

MANIFEST_DIR = Path(__file__).resolve().parent.parent / "manifests"


@dataclass
class Manifest:
    numero: str
    classe: str | None = None
    titulo: str | None = None
    vara: str | None = None
    distribuido_em: str | None = None
    ultima_movimentacao: str | None = None
    ultima_movimentacao_desc: str | None = None
    pje_id: str | None = None
    pje_ca: str | None = None
    pecas: dict[str, str] = field(default_factory=dict)  # id -> sha256
    ultima_coleta: str | None = None
    ultima_analise: str | None = None

    @classmethod
    def load(cls, numero: str) -> "Manifest | None":
        path = MANIFEST_DIR / f"{numero}.json"
        if not path.exists():
            return None
        return cls(**json.loads(path.read_text(encoding="utf-8")))

    def save(self) -> None:
        MANIFEST_DIR.mkdir(parents=True, exist_ok=True)
        path = MANIFEST_DIR / f"{self.numero}.json"
        path.write_text(
            json.dumps(asdict(self), ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )


def diff_acervo(items: list[ProcessoAcervo]) -> list[ProcessoAcervo]:
    """Retorna apenas processos novos ou com movimentação posterior ao manifest."""
    pendentes: list[ProcessoAcervo] = []
    for p in items:
        m = Manifest.load(p.numero)
        if m is None:
            pendentes.append(p)
            continue
        if p.ultima_movimentacao and p.ultima_movimentacao != m.ultima_movimentacao:
            pendentes.append(p)
    return pendentes
