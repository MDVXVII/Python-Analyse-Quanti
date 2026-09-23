"""Journal horodaté des recommandations : append-only, chaîné par hachage SHA-256.

Chaque ligne (JSON) contient l'empreinte de la ligne précédente : modifier ou supprimer
une recommandation passée casse la chaîne, ce que :meth:`Journal.verify` détecte.
Chaque jour, l'empreinte de tête est écrite dans ``commitments/<date>.json`` (versionné
dans le dépôt public) : c'est un **engagement** vérifiable qui prouve, plus tard, que les
recommandations existaient à cette date, sans les divulguer (ARCHITECTURE.md §1).
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd

GENESIS = "0" * 64


def _canonical(obj: dict[str, Any]) -> bytes:
    return json.dumps(
        obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"), default=str
    ).encode("utf-8")


def entry_hash(entry: dict[str, Any]) -> str:
    body = {k: v for k, v in entry.items() if k != "hash"}
    return hashlib.sha256(_canonical(body)).hexdigest()


class JournalError(RuntimeError):
    pass


class Journal:
    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def _lines(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        return [
            json.loads(line)
            for line in self.path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]

    def head(self) -> tuple[str, int]:
        lines = self._lines()
        return (lines[-1]["hash"], len(lines)) if lines else (GENESIS, 0)

    def append(self, records: Iterable[dict[str, Any]]) -> tuple[str, int]:
        """Ajoute des recommandations ; refuse d'écrire sur une chaîne corrompue."""
        ok, _, problem = self.verify()
        if not ok:
            raise JournalError(f"journal corrompu, écriture refusée : {problem}")
        prev, seq = self.head()
        with self.path.open("a", encoding="utf-8") as fh:
            for rec in records:
                entry = {
                    **rec,
                    "seq": seq + 1,
                    "prev_hash": prev,
                    "recorded_at": datetime.now(UTC).isoformat(timespec="seconds"),
                }
                entry["hash"] = entry_hash(entry)
                fh.write(_canonical(entry).decode("utf-8") + "\n")
                prev, seq = entry["hash"], seq + 1
        return prev, seq

    def verify(self) -> tuple[bool, int, str | None]:
        """Vérifie toute la chaîne : (valide, nombre de lignes, description du problème)."""
        prev = GENESIS
        lines = self._lines()
        for i, entry in enumerate(lines, start=1):
            if entry.get("seq") != i:
                return False, len(lines), f"numéro de séquence inattendu à la ligne {i}"
            if entry.get("prev_hash") != prev:
                return False, len(lines), f"chaînage rompu à la ligne {i}"
            if entry_hash(entry) != entry.get("hash"):
                return False, len(lines), f"contenu modifié à la ligne {i}"
            prev = entry["hash"]
        return True, len(lines), None

    def to_frame(self) -> pd.DataFrame:
        return pd.DataFrame(self._lines())

    def write_commitment(
        self, day: str, directory: Path, extra: dict[str, Any] | None = None
    ) -> Path:
        head, count = self.head()
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / f"{day}.json"
        payload = {"date": day, "journal_head_sha256": head, "entries": count, **(extra or {})}
        path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        return path
