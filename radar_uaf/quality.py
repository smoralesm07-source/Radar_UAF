from __future__ import annotations

from collections import Counter
from datetime import date, datetime

from .storage import read_jsonl, table_path
from .utils import normalize_name

STALE_SEED_DAYS = 45


def _days_since(iso_date: str) -> int | None:
    try:
        parsed = datetime.fromisoformat(iso_date[:19])
        return (datetime.utcnow() - parsed).days
    except Exception:
        return None


def evaluate_consistency() -> dict:
    """Evalua la consistencia de los datos recolectados: duplicados por nombre normalizado,
    campos criticos faltantes, mezcla de procedencia (seed vs. vivo) y antiguedad de hechos
    semilla aun no confirmados por una corrida en linea. No corrige datos: solo diagnostica,
    dejando la decision de depuracion a una revision posterior (igual criterio que el quality
    gate de Radar-CGR, que separa deteccion de remediacion)."""
    documents = read_jsonl(table_path("documents"))
    entities = read_jsonl(table_path("entities"))
    sanctions = read_jsonl(table_path("sanctions"))
    statistics = read_jsonl(table_path("statistics"))
    watch_items = read_jsonl(table_path("watch_items"))

    name_counts = Counter(normalize_name(e.get("name", "")) for e in entities if e.get("name"))
    duplicate_entity_names = {name: count for name, count in name_counts.items() if count > 1 and name}

    documents_missing_date = [d.get("document_id") for d in documents if not d.get("document_date")]
    documents_missing_url = [d.get("document_id") for d in documents if not d.get("source_url")]
    sanctions_missing_amount = sum(1 for s in sanctions if s.get("amount_uf") in (None, 0))

    capture_methods = Counter(s.get("capture_method", "UNKNOWN") for s in statistics)
    document_status = Counter(d.get("status", "UNKNOWN") for d in documents)

    stale_seed = []
    for doc in documents:
        if doc.get("status") != "SEED_PENDING_LIVE_CONFIRMATION":
            continue
        age = _days_since(doc.get("retrieved_at", ""))
        if age is not None and age > STALE_SEED_DAYS:
            stale_seed.append(doc.get("document_id"))

    open_watch = sum(1 for w in watch_items if w.get("status") == "OPEN")

    checks = [
        {
            "id": "duplicate_entity_names",
            "label": "Entidades con el mismo nombre normalizado",
            "severity": "MEDIUM" if duplicate_entity_names else "OK",
            "count": len(duplicate_entity_names),
            "detail": list(duplicate_entity_names.items())[:20],
        },
        {
            "id": "documents_missing_date",
            "label": "Documentos sin fecha reconocida",
            "severity": "LOW" if documents_missing_date else "OK",
            "count": len(documents_missing_date),
        },
        {
            "id": "documents_missing_url",
            "label": "Documentos sin URL fuente",
            "severity": "HIGH" if documents_missing_url else "OK",
            "count": len(documents_missing_url),
        },
        {
            "id": "sanctions_missing_amount",
            "label": "Sanciones sin monto UF identificado",
            "severity": "LOW" if sanctions_missing_amount else "OK",
            "count": sanctions_missing_amount,
        },
        {
            "id": "stale_seed_facts",
            "label": f"Hechos semilla sin confirmar en vivo por mas de {STALE_SEED_DAYS} dias",
            "severity": "MEDIUM" if stale_seed else "OK",
            "count": len(stale_seed),
            "detail": stale_seed[:20],
        },
        {
            "id": "unknown_normativa_status",
            "label": "Normativa con estado de vigencia desconocido",
            "severity": "MEDIUM" if document_status.get("UNKNOWN", 0) else "OK",
            "count": document_status.get("UNKNOWN", 0),
        },
    ]

    return {
        "generated_at": datetime.utcnow().replace(microsecond=0).isoformat() + "Z",
        "checks": checks,
        "capture_method_mix": [{"name": k, "count": v} for k, v in capture_methods.most_common()],
        "document_status_mix": [{"name": k, "count": v} for k, v in document_status.most_common()],
        "open_watch_items": open_watch,
        "overall_status": "REVIEW_RECOMMENDED" if any(c["severity"] in ("MEDIUM", "HIGH") for c in checks) else "OK",
    }
