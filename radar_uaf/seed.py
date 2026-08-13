from __future__ import annotations

from .config import load_seed_facts
from .extract import seed_fact_to_records
from .storage import upsert_jsonl


def load_seed_into_silver() -> dict:
    """Materializa config/seed_facts.json (hechos publicos verificados manualmente via OSINT,
    con fuente citada) como Document/Statistic/Event de arranque. Es idempotente: correr esto
    de nuevo no duplica filas porque upsert_jsonl compara por clave estable. Estos registros
    quedan marcados capture_method=SEED_OSINT_SUMMARY / status=SEED_PENDING_LIVE_CONFIRMATION
    para distinguirlos de datos obtenidos por el colector en vivo."""
    payload = load_seed_facts()
    documents, statistics, events = [], [], []
    for fact in payload.get("facts", []):
        doc, stat, event = seed_fact_to_records(fact)
        documents.append(doc.to_dict())
        events.append(event.to_dict())
        if stat is not None:
            statistics.append(stat.to_dict())
    doc_result = upsert_jsonl("documents", documents, "document_id")
    stat_result = upsert_jsonl("statistics", statistics, "statistic_id") if statistics else (0, 0)
    event_result = upsert_jsonl("events", events, "event_id")
    return {
        "seed_documents": doc_result,
        "seed_statistics": stat_result,
        "seed_events": event_result,
        "facts_loaded": len(payload.get("facts", [])),
    }
