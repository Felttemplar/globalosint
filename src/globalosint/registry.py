"""Operações de cadastro e avaliação do Source Registry."""

import json
import sqlite3
from urllib.parse import urlparse

from globalosint.models import Axis, Language, Source, SourceInput, SourceKind, SourceStatus


def _validate_url(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("A URL da fonte deve ser absoluta e usar HTTP ou HTTPS")


def _validate_codes(values: tuple[str, ...], allowed: set[str], label: str) -> None:
    unknown = set(values) - allowed
    if unknown:
        raise ValueError(f"{label} inválido(s): {', '.join(sorted(unknown))}")


def add_source(connection: sqlite3.Connection, source: SourceInput) -> Source:
    name = source.name.strip()
    if not name:
        raise ValueError("O nome da fonte não pode ficar vazio")
    _validate_url(source.url)
    _validate_codes(source.languages, {item.value for item in Language}, "Idioma")
    _validate_codes(source.axes, {item.value for item in Axis}, "Eixo")
    cursor = connection.execute(
        """INSERT INTO sources(name,url,kind,languages_json,axes_json,notes)
           VALUES(?,?,?,?,?,?)""",
        (name, source.url, source.kind.value, json.dumps(sorted(set(source.languages))),
         json.dumps(sorted(set(source.axes))), source.notes),
    )
    row = connection.execute("SELECT * FROM sources WHERE id=?", (cursor.lastrowid,)).fetchone()
    return _row_to_source(row)


def list_sources(connection: sqlite3.Connection, status: SourceStatus | None = None) -> list[Source]:
    if status is None:
        rows = connection.execute("SELECT * FROM sources ORDER BY name COLLATE NOCASE")
    else:
        rows = connection.execute(
            "SELECT * FROM sources WHERE status=? ORDER BY name COLLATE NOCASE", (status.value,)
        )
    return [_row_to_source(row) for row in rows]


def assess_source(
    connection: sqlite3.Connection,
    source_id: int,
    status: SourceStatus,
    reliability_score: int | None,
    notes: str | None = None,
) -> Source:
    if reliability_score is not None and not 0 <= reliability_score <= 100:
        raise ValueError("A avaliação de confiabilidade deve estar entre 0 e 100")
    cursor = connection.execute(
        """UPDATE sources SET status=?, reliability_score=?,
           notes=COALESCE(?, notes), updated_at=strftime('%Y-%m-%dT%H:%M:%fZ','now') WHERE id=?""",
        (status.value, reliability_score, notes, source_id),
    )
    if cursor.rowcount == 0:
        raise LookupError(f"Fonte {source_id} não encontrada")
    return _row_to_source(connection.execute("SELECT * FROM sources WHERE id=?", (source_id,)).fetchone())


def _row_to_source(row: sqlite3.Row) -> Source:
    return Source(
        id=row["id"], name=row["name"], url=row["url"], kind=SourceKind(row["kind"]),
        languages=tuple(json.loads(row["languages_json"])), axes=tuple(json.loads(row["axes_json"])),
        status=SourceStatus(row["status"]), reliability_score=row["reliability_score"], notes=row["notes"],
    )
