from __future__ import annotations

from .config import load_official_statistics, load_seed_facts
from .extract import seed_fact_to_records
from .models import Statistic, stable_id
from .storage import upsert_jsonl


def load_seed_into_silver() -> dict:
    """Materializa hechos históricos OSINT como registros auxiliares.

    Desde v0.2 las cifras vigentes de sujetos obligados y las estadísticas anuales oficiales
    no dependen de esta semilla: se obtienen del XLSX vigente y del Informe Estadístico UAF.
    """
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


def load_official_statistics_into_silver() -> dict:
    """Carga las series oficiales del Informe Estadístico UAF 2025.

    Los identificadores coinciden con los usados por el extractor PDF en vivo. Cuando la
    corrida en línea encuentra el mismo indicador/año, reemplaza la observación curada y
    conserva una única fila por métrica y período.
    """
    payload = load_official_statistics()
    source_url = payload.get("source_url", "")
    method = payload.get("capture_method", "OFFICIAL_UAF_REPORT")
    observations: list[dict] = []

    for series in payload.get("series", []):
        metric = series.get("metric", "")
        category = series.get("category", "GENERAL")
        unit = series.get("unit", "")
        for period, value in (series.get("values") or {}).items():
            observations.append(
                Statistic(
                    statistic_id=stable_id("STAT", "UAF_ANNUAL", metric, period),
                    metric=metric,
                    category=category,
                    value=float(value),
                    unit=unit,
                    period=str(period),
                    as_of_date=f"{period}-12-31" if str(period).isdigit() else "",
                    source_url=source_url,
                    capture_method=method,
                    confidence=1.0,
                ).to_dict()
            )

    for item in payload.get("latest_metrics", []):
        metric = item.get("metric", "")
        period = str(item.get("period") or (item.get("as_of_date", "")[:4]))
        observations.append(
            Statistic(
                statistic_id=stable_id("STAT", "UAF_ANNUAL", metric, period),
                metric=metric,
                category=item.get("category", "GENERAL"),
                value=float(item.get("value", 0)),
                unit=item.get("unit", ""),
                period=period,
                as_of_date=item.get("as_of_date", ""),
                source_url=source_url,
                capture_method=method,
                confidence=1.0,
            ).to_dict()
        )

    result = upsert_jsonl("statistics", observations, "statistic_id") if observations else (0, 0)
    return {"observations": len(observations), "upsert": result, "source_url": source_url}
