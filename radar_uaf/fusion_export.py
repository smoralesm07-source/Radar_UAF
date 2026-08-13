from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Iterable

RADAR_ID = "RADAR_UAF"
VERSION = "1.0"


def _read_jsonl(path: Path) -> Iterable[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def _write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
            count += 1
    return count


def _evidence_id(seed: str) -> str:
    return "EVD-UAF-" + hashlib.sha256(seed.encode("utf-8")).hexdigest()[:24]


def _iso_date(value: object) -> str | None:
    text = str(value or "").strip()
    if not text:
        return None
    if len(text) == 10:
        return text + "T00:00:00+00:00"
    return text


def build(root: Path) -> dict[str, int]:
    silver = root / "data" / "silver"
    documents = list(_read_jsonl(silver / "documents.jsonl"))
    events = list(_read_jsonl(silver / "events.jsonl"))
    hub = list(_read_jsonl(silver / "entity_hub_v1.jsonl"))

    documents_by_id = {str(row.get("document_id") or ""): row for row in documents if row.get("document_id")}
    evidence: dict[str, dict[str, Any]] = {}

    def evidence_from_document(document: dict[str, Any]) -> str:
        document_id = str(document.get("document_id") or "")
        seed = document_id or "|".join([
            str(document.get("source_url") or ""),
            str(document.get("retrieved_at") or ""),
            str(document.get("title") or ""),
        ])
        eid = _evidence_id(seed)
        evidence[eid] = {
            "evidence_id": eid,
            "producer_id": RADAR_ID,
            "source_id": str(document.get("source_module") or document.get("source_system") or "UAF"),
            "ultimate_source_id": str(document.get("source_system") or "UAF"),
            "source_url": document.get("source_url") or None,
            "source_tier": "OFFICIAL" if str(document.get("source_system") or "").upper() == "UAF" else "PUBLIC_OSINT",
            "capture_method": "RADAR_UAF_SILVER_DOCUMENT",
            "source_run_id": None,
            "content_sha256": document.get("content_hash") or None,
            "quality_status": "VALID" if str(document.get("status") or "").upper() not in {"FAILED", "ERROR"} else "FAILED",
            "source_published_at": _iso_date(document.get("document_date")),
            "retrieved_at": str(document.get("retrieved_at") or ""),
            "ingested_at": str(document.get("retrieved_at") or ""),
            "excerpt": document.get("raw_text_excerpt") or None,
            "schema_version": VERSION,
        }
        return eid

    for document in documents:
        evidence_from_document(document)

    canonical_events: list[dict[str, Any]] = []
    for row in events:
        document_id = str(row.get("document_id") or "")
        if document_id and document_id in documents_by_id:
            eid = evidence_from_document(documents_by_id[document_id])
        else:
            seed = "|".join([str(row.get("event_id") or ""), str(row.get("source_url") or ""), str(row.get("retrieved_at") or "")])
            eid = _evidence_id(seed)
            evidence[eid] = {
                "evidence_id": eid,
                "producer_id": RADAR_ID,
                "source_id": str(row.get("source_module") or "UAF_EVENT"),
                "ultimate_source_id": "UAF",
                "source_url": row.get("source_url") or None,
                "source_tier": "OFFICIAL_OR_GOVERNED",
                "capture_method": "RADAR_UAF_SILVER_EVENT",
                "source_run_id": None,
                "content_sha256": None,
                "quality_status": "VALID",
                "source_published_at": _iso_date(row.get("event_date")),
                "retrieved_at": str(row.get("retrieved_at") or ""),
                "ingested_at": str(row.get("retrieved_at") or ""),
                "schema_version": VERSION,
            }
        canonical_events.append({
            "event_id": str(row.get("event_id") or ""),
            "event_type": str(row.get("event_type") or "UAF_OBSERVATION"),
            "producer_id": RADAR_ID,
            "entity_ids": [],
            "territory_ids": [],
            "sector_ids": [],
            "evidence_ids": [eid],
            "temporal": {
                "valid_from": _iso_date(row.get("event_date")),
                "valid_to": None,
                "source_published_at": _iso_date(row.get("event_date")),
                "observed_at": str(row.get("retrieved_at") or "") or None,
                "retrieved_at": str(row.get("retrieved_at") or "") or None,
                "ingested_at": str(row.get("retrieved_at") or "") or None,
                "last_seen_at": None,
                "freshness_state": "CURRENT",
            },
            "attributes": {
                "document_id": document_id or None,
                "source_module": row.get("source_module") or None,
                "status": row.get("status") or None,
                "title": row.get("title") or None,
                "entity_name_unresolved": row.get("entity_name") or None,
            },
        })

    canonical_entities: list[dict[str, Any]] = []
    for row in hub:
        entity_id = str(row.get("entity_id") or "")
        if not entity_id.startswith("ENT-RUT-"):
            continue
        doc_id = str(row.get("source_document_id") or "")
        if doc_id and doc_id in documents_by_id:
            eid = evidence_from_document(documents_by_id[doc_id])
        else:
            eid = _evidence_id("entity|" + entity_id + "|" + str(row.get("source_entity_id") or ""))
            evidence[eid] = {
                "evidence_id": eid,
                "producer_id": RADAR_ID,
                "source_id": "UAF_ENTITY_HUB",
                "ultimate_source_id": "UAF",
                "source_url": None,
                "source_tier": "GOVERNED_DERIVED",
                "capture_method": "RADAR_UAF_ENTITY_HUB",
                "source_run_id": None,
                "content_sha256": None,
                "quality_status": "PARTIAL",
                "source_published_at": None,
                "retrieved_at": "1970-01-01T00:00:00+00:00",
                "ingested_at": None,
                "schema_version": VERSION,
            }
        canonical_entities.append({
            "entity_id": entity_id,
            "entity_type": "PUBLIC_BODY" if str(row.get("entity_role") or "") == "PUBLIC_BODY" else "LEGAL_ENTITY",
            "canonical_name": row.get("canonical_name") or None,
            "rut_normalized": row.get("rut") or None,
            "aliases": [],
            "roles": [str(row.get("entity_role") or "SOURCE_ENTITY")],
            "producer_ids": [RADAR_ID],
            "evidence_ids": [eid],
            "identity_method": "RUT_EXACT",
            "identity_confidence": 1.0,
            "attributes": {"source_entity_id": row.get("source_entity_id") or None},
        })

    evidence_count = _write_jsonl(silver / "evidence_v1.jsonl", evidence.values())
    entity_count = _write_jsonl(silver / "entities_fusion_v1.jsonl", canonical_entities)
    event_count = _write_jsonl(silver / "events_fusion_v1.jsonl", canonical_events)
    status = {"interop_version": VERSION, "radar_id": RADAR_ID, "status": "FUSION_EXPORT_READY", "evidence": evidence_count, "entities": entity_count, "events": event_count}
    (root / "docs" / "data" / "fusion_interop_status_v1.json").write_text(json.dumps(status, ensure_ascii=False, indent=2), encoding="utf-8")
    return status
