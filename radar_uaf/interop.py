from __future__ import annotations

import re
from typing import Any

from .storage import read_jsonl, replace_jsonl, table_path
from .utils import normalize_name

INTEROP_VERSION = "1.0"
RADAR_ID = "RADAR_UAF"


def _rut_dv(body: str) -> str:
    total = 0
    multiplier = 2
    for digit in reversed(body):
        total += int(digit) * multiplier
        multiplier = multiplier + 1 if multiplier < 7 else 2
    result = 11 - (total % 11)
    return "0" if result == 11 else ("K" if result == 10 else str(result))


def normalize_rut(value: object) -> str | None:
    compact = re.sub(r"[^0-9Kk]", "", str(value or "")).upper()
    if not re.fullmatch(r"\d{1,8}[0-9K]", compact):
        return None
    body, dv = compact[:-1], compact[-1]
    if _rut_dv(body) != dv:
        return None
    return f"{int(body)}-{dv}"


def global_entity_id(rut: object) -> str | None:
    canonical = normalize_rut(rut)
    return f"ENT-RUT-{canonical}" if canonical else None


def _role(entity_type: str) -> str:
    value = str(entity_type or "").upper()
    if "SUJETO_OBLIGADO" in value:
        return "OBLIGED_ENTITY"
    if "SANCIONADO" in value:
        return "SANCTIONED_ENTITY"
    if "PUBLIC" in value or "PUBLICO" in value:
        return "PUBLIC_BODY"
    return "SOURCE_ENTITY"


def adapt_entity_record(record: dict[str, Any], role: str | None = None) -> dict[str, Any]:
    rut = normalize_rut(record.get("rut"))
    eid = global_entity_id(rut)
    source_entity_id = str(record.get("entity_id") or record.get("source_entity_id") or "")
    name = str(record.get("name") or record.get("entity_name") or record.get("canonical_name") or "")
    resolved = bool(eid)
    return {
        "interop_version": INTEROP_VERSION,
        "radar_id": RADAR_ID,
        "entity_id": eid,
        "source_entity_id": source_entity_id or None,
        "candidate_entity_id": None if resolved else (source_entity_id or None),
        "entity_type": record.get("entity_type") or "LEGAL_ENTITY",
        "entity_role": role or _role(str(record.get("entity_type") or "")),
        "rut": rut,
        "rut_valid": resolved,
        "canonical_name": name,
        "normalized_name": record.get("normalized_name") or normalize_name(name),
        "identity_status": "RESOLVED" if resolved else "UNRESOLVED",
        "identity_method": "RUT_EXACT" if resolved else "SOURCE_LOCAL_ONLY",
        "identity_confidence": 1.0 if resolved else 0.0,
        "candidate_confidence": None if resolved else float(record.get("confidence") or 0.0),
        "source_document_id": record.get("source_document_id") or record.get("document_id") or "",
    }


def materialize_entity_hub() -> dict[str, int]:
    rows: dict[str, dict] = {}
    for entity in read_jsonl(table_path("entities")):
        adapted = adapt_entity_record(entity)
        key = adapted.get("source_entity_id")
        if key:
            rows[str(key)] = adapted

    # Legacy sanctions often have only a name-derived local ID. They remain explicit
    # candidates and never become global identities without a valid RUT.
    for sanction in read_jsonl(table_path("sanctions")):
        source_id = str(sanction.get("entity_id") or "")
        if not source_id or source_id in rows:
            continue
        adapted = adapt_entity_record(
            {
                "entity_id": source_id,
                "entity_name": sanction.get("entity_name") or "",
                "document_id": sanction.get("document_id") or "",
                "entity_type": "SANCIONADO_ORGANIZACION",
                "confidence": 0.5,
            },
            role="SANCTIONED_ENTITY",
        )
        rows[source_id] = adapted

    inserted, updated, deleted = replace_jsonl(
        "entity_hub_v1", rows.values(), "source_entity_id"
    )
    return {
        "rows": len(rows),
        "resolved": sum(bool(x.get("entity_id")) for x in rows.values()),
        "unresolved": sum(not bool(x.get("entity_id")) for x in rows.values()),
        "inserted": inserted,
        "updated": updated,
        "deleted": deleted,
    }
