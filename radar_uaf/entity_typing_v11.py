from __future__ import annotations

import json
from pathlib import Path


def apply_entity_typing(root: Path) -> dict:
    path = root / "data" / "silver" / "entities_fusion_v1.jsonl"
    rows = []
    explicit = 0
    unknown = 0
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        roles = {str(x).strip().upper() for x in row.get("roles", [])}
        if "PUBLIC_BODY" in roles:
            row["entity_type"] = "PUBLIC_BODY"
            method = "SOURCE_EXPLICIT_ROLE"
            confidence = 1.0
            explicit += 1
        else:
            row["entity_type"] = "UNKNOWN"
            method = "SOURCE_UNSPECIFIED"
            confidence = 0.0
            unknown += 1
        attrs = dict(row.get("attributes") or {})
        attrs["entity_type_method"] = method
        attrs["entity_type_confidence"] = confidence
        attrs["entity_type_policy"] = "UNKNOWN_UNLESS_SOURCE_EXPLICIT"
        row["attributes"] = attrs
        rows.append(row)
    path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")
    status_path = root / "docs" / "data" / "fusion_interop_status_v1.json"
    status = json.loads(status_path.read_text(encoding="utf-8")) if status_path.exists() else {}
    status.update({
        "interop_version": "1.1",
        "status": "FUSION_EXPORT_READY_ENTITY_TYPING_CONSERVATIVE",
        "entity_types_explicit": explicit,
        "entity_types_unknown": unknown,
        "entity_type_policy": "UNKNOWN_UNLESS_SOURCE_EXPLICIT",
        "source_failure_is_zero": False,
    })
    status_path.write_text(json.dumps(status, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"entities": len(rows), "entity_types_explicit": explicit, "entity_types_unknown": unknown}
