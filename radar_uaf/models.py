from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any


def utcnow_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def stable_id(prefix: str, *parts: Any) -> str:
    """ID determinista y estable entre corridas, reutilizado como convencion para permitir
    cruces futuros con otros radares (Radar-CGR, Radar-SII, Radar-Sectorial) sobre un mismo
    espacio de identificadores por tipo de entidad."""
    normalized = "|".join(str(p or "").strip().upper() for p in parts)
    digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:20]
    return f"{prefix}-{digest}"


@dataclass
class Document:
    document_id: str
    source_system: str
    source_module: str
    source_url: str
    title: str = ""
    document_type: str = ""  # LEY | CIRCULAR | INFORME_TIPOLOGIAS | NOTICIA | FAQ | DATASET
    document_number: str = ""
    document_date: str = ""
    status: str = ""  # VIGENTE | DEROGADA | UNKNOWN
    content_hash: str = ""
    retrieved_at: str = field(default_factory=utcnow_iso)
    raw_text_excerpt: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Event:
    event_id: str
    document_id: str
    event_type: str  # NORMATIVA_PUBLICADA | SANCION_EJECUTORIADA | INFORME_PUBLICADO | NOTICIA | DATASET_ACTUALIZADO
    event_date: str
    title: str
    entity_name: str = ""
    source_url: str = ""
    source_module: str = ""
    status: str = "PUBLISHED"
    retrieved_at: str = field(default_factory=utcnow_iso)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Entity:
    """Nodo comun para sujetos obligados, entidades sancionadas y organismos del sector
    publico. Pensado como el punto de union del futuro Entity Hub compartido entre radares:
    misma forma (entity_id, entity_type, name, normalized_name, rut) que Radar-CGR."""

    entity_id: str
    entity_type: str  # SUJETO_OBLIGADO | SANCIONADO_PERSONA | SANCIONADO_ORGANIZACION | ORGANISMO_PUBLICO
    name: str
    normalized_name: str
    rut: str = ""
    sector: str = ""
    activity: str = ""
    source_document_id: str = ""
    confidence: float = 0.6

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Sanction:
    sanction_id: str
    document_id: str
    entity_id: str
    entity_name: str
    resolution_number: str = ""
    resolution_date: str = ""
    severity: str = "UNKNOWN"  # LEVE | MENOS_GRAVE | GRAVE | UNKNOWN
    sanction_type: str = ""  # AMONESTACION | MULTA | UNKNOWN
    amount_uf: float | None = None
    reason_summary: str = ""
    source_url: str = ""
    retrieved_at: str = field(default_factory=utcnow_iso)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Statistic:
    statistic_id: str
    metric: str
    category: str
    value: float
    unit: str = ""
    period: str = ""
    as_of_date: str = ""
    source_url: str = ""
    capture_method: str = "LIVE_SCRAPE"  # LIVE_SCRAPE | CKAN_API | SEED_OSINT_SUMMARY
    confidence: float = 0.6
    retrieved_at: str = field(default_factory=utcnow_iso)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class WatchItem:
    watch_id: str
    source_id: str
    watch_type: str  # NORMATIVA_CAMBIO | SANCION_NUEVA | DATASET_CAMBIO
    title: str
    source_url: str
    stage: str = "WATCH"
    first_seen: str = field(default_factory=utcnow_iso)
    last_seen: str = field(default_factory=utcnow_iso)
    status: str = "OPEN"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class SourceRun:
    run_id: str
    source_id: str
    source_name: str
    source_url: str
    started_at: str
    finished_at: str
    status: str  # OK | ERROR | SKIPPED_NO_NETWORK
    http_status: int | None = None
    content_hash: str = ""
    items_found: int = 0
    error: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def canonical_json(obj: dict[str, Any]) -> str:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
