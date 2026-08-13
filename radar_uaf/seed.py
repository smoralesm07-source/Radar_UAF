from __future__ import annotations

from .config import load_official_statistics, load_seed_facts
from .extract import seed_fact_to_records
from .models import Statistic, stable_id
from .storage import read_jsonl, replace_jsonl, table_path, upsert_jsonl


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


def _clean_misdated_official_report_rows(source_url: str, official_year: str) -> dict:
    """Migración defensiva v0.2.

    Durante la construcción de v0.2 una validación detectó que el año de publicación del bloque
    HTML podía confundirse con el período del PDF. Eliminamos únicamente filas LIVE asociadas al
    archivo oficial conocido cuyo período no coincide con el año del documento.
    """
    stats = read_jsonl(table_path("statistics"))
    clean_stats = [
        row
        for row in stats
        if not (
            row.get("capture_method") == "LIVE_OFFICIAL_UAF_REPORT"
            and row.get("source_url") == source_url
            and str(row.get("period", ""))
            and str(row.get("period")) != official_year
        )
    ]
    stat_deleted = 0
    if len(clean_stats) != len(stats):
        _, _, stat_deleted = replace_jsonl("statistics", clean_stats, "statistic_id")

    docs = read_jsonl(table_path("documents"))
    clean_docs = [
        row
        for row in docs
        if not (
            row.get("document_type") == "INFORME_ESTADISTICO"
            and row.get("source_url") == source_url
            and row.get("document_date", "")[:4]
            and row.get("document_date", "")[:4] != official_year
        )
    ]
    doc_deleted = 0
    if len(clean_docs) != len(docs):
        _, _, doc_deleted = replace_jsonl("documents", clean_docs, "document_id")
    return {"statistics_deleted": stat_deleted, "documents_deleted": doc_deleted}


def load_official_statistics_into_silver() -> dict:
    """Carga las series oficiales del Informe Estadístico UAF 2025.

    Los identificadores coinciden con los usados por el extractor PDF en vivo. Cuando la
    corrida en línea encuentra el mismo indicador/año, reemplaza la observación curada y
    conserva una única fila por métrica y período.
    """
    payload = load_official_statistics()
    source_url = payload.get("source_url", "")
    official_year = str(payload.get("version", ""))
    cleanup = _clean_misdated_official_report_rows(source_url, official_year) if source_url and official_year else {}
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
    return {"observations": len(observations), "upsert": result, "source_url": source_url, "cleanup": cleanup}
