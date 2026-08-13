from __future__ import annotations

import json
from collections import Counter, defaultdict

from .config import DOCS_DIR
from .coverage import summarize_coverage
from .quality import evaluate_consistency
from .storage import read_jsonl, table_path

DISCLAIMER = (
    "Radar UAF transforma información publicada por la Unidad de Análisis Financiero de Chile "
    "y por el Portal de Datos Abiertos en datos estructurados para priorización analítica AML/LA-FT. "
    "Las cifras de registro vigente se obtienen del archivo oficial publicado por la UAF y se muestran "
    "con su fecha de corte. Las series anuales provienen del Informe Estadístico UAF. Una sanción, cifra "
    "agregada o coincidencia con una lista no acredita por sí sola lavado de activos, financiamiento del "
    "terrorismo, dolo ni responsabilidad individual."
)

IMPROVEMENT_BACKLOG = [
    {
        "id": "individual-sanction-records",
        "area": "Extracción",
        "priority": "ALTA",
        "title": "Extraer resoluciones sancionatorias individuales y entidades involucradas",
        "detail": "v0.2 corrige sujetos obligados y estadísticas. El siguiente foco es resolver la sección moderna de sanciones ejecutoriadas, abrir cada resolución y estructurar entidad, RUT cuando sea público, fecha, infracción, monto UF y resolución para análisis de recurrencia.",
    },
    {
        "id": "registry-diff",
        "area": "Sujetos obligados",
        "priority": "ALTA",
        "title": "Generar altas, bajas y cambios entre cortes semestrales del registro UAF",
        "detail": "El XLSX vigente ya se ingiere a nivel RUT. La siguiente mejora es comparar cada corte contra el anterior y generar eventos por inscripción, salida o cambio de actividad, conservando trazabilidad temporal.",
    },
    {
        "id": "ckan-resource-series",
        "area": "Datos abiertos",
        "priority": "MEDIA",
        "title": "Descargar recursos CKAN para complementar las series oficiales",
        "detail": "El Informe Estadístico ya aporta series 2021-2025. Falta descargar los recursos CSV/XLSX de datos.gob.cl para ampliar granularidad mensual/anual en ROS, comisos y procesos judiciales y contrastarlos con el informe institucional.",
    },
    {
        "id": "entity-hub-crosslink",
        "area": "Arquitectura",
        "priority": "ALTA",
        "title": "Consolidar identificadores RUT para cruces futuros entre radares",
        "detail": "v0.2 incorpora sujetos obligados como entidades estructuradas por RUT. Esto habilita el futuro cruce con Radar SII, Radar CGR y otros radares sin depender de coincidencias solo por nombre.",
    },
    {
        "id": "onu-list-diffing",
        "area": "Sanciones internacionales",
        "priority": "MEDIA",
        "title": "Versionar Listas de Resoluciones ONU y detectar altas/bajas",
        "detail": "Capturar snapshot completo y generar diferencias entre corridas por persona o entidad agregada/retirada.",
    },
]

QUESTION_CATALOG = [
    {"id": "sujetos_obligados", "label": "¿Cuántos sujetos obligados están inscritos en el último corte UAF?"},
    {"id": "estadisticas", "label": "¿Cómo evolucionan ROS, ROE, entidades reportantes y supervisión?"},
    {"id": "sanciones", "label": "¿Qué entidades y montos concentran las sanciones UAF?"},
    {"id": "normativa", "label": "¿Qué circulares están vigentes y cuáles fueron derogadas?"},
    {"id": "calidad", "label": "¿Qué tan consistentes y actuales están los datos del radar?"},
    {"id": "mejoras", "label": "¿Qué mejoras están priorizadas para las próximas versiones?"},
]

METHOD_RANK = {
    "UAF_REGISTRY_XLSX": 5,
    "LIVE_OFFICIAL_UAF_REPORT": 5,
    "OFFICIAL_UAF_REPORT": 4,
    "CKAN_API": 3,
    "LIVE_SCRAPE": 2,
    "SEED_OSINT_SUMMARY": 1,
}


def _date_key(row: dict) -> str:
    value = row.get("as_of_date") or row.get("period") or ""
    if len(value) == 4 and value.isdigit():
        return f"{value}-12-31"
    return value


def _latest_by_metric(statistics: list[dict]) -> dict[str, dict]:
    latest: dict[str, dict] = {}
    for row in statistics:
        metric = row.get("metric", "")
        if not metric:
            continue
        key = (_date_key(row), METHOD_RANK.get(row.get("capture_method", ""), 0), row.get("retrieved_at", ""))
        current = latest.get(metric)
        if current is None:
            latest[metric] = row
            continue
        current_key = (
            _date_key(current),
            METHOD_RANK.get(current.get("capture_method", ""), 0),
            current.get("retrieved_at", ""),
        )
        if key > current_key:
            latest[metric] = row
    return latest


def _series(statistics: list[dict]) -> list[dict]:
    """Agrupa observaciones por indicador y elimina duplicados de un mismo período/corte,
    priorizando extracción oficial en vivo > serie oficial curada > metadatos/semillas."""
    grouped: dict[str, dict[str, dict]] = defaultdict(dict)
    for row in statistics:
        metric = row.get("metric", "")
        if not metric or metric == "dataset_recursos_publicados":
            continue
        point = row.get("period") or row.get("as_of_date") or "sin_fecha"
        current = grouped[metric].get(point)
        rank = (METHOD_RANK.get(row.get("capture_method", ""), 0), _date_key(row), row.get("retrieved_at", ""))
        if current is None:
            grouped[metric][point] = row
        else:
            current_rank = (
                METHOD_RANK.get(current.get("capture_method", ""), 0),
                _date_key(current),
                current.get("retrieved_at", ""),
            )
            if rank > current_rank:
                grouped[metric][point] = row

    output = []
    for metric, points in grouped.items():
        rows = sorted(points.values(), key=lambda x: _date_key(x))
        if not rows:
            continue
        output.append(
            {
                "metric": metric,
                "category": rows[-1].get("category", ""),
                "unit": rows[-1].get("unit", ""),
                "points": [
                    {
                        "period": r.get("period") or r.get("as_of_date") or "—",
                        "as_of_date": r.get("as_of_date", ""),
                        "value": r.get("value"),
                        "capture_method": r.get("capture_method", ""),
                        "source_url": r.get("source_url", ""),
                    }
                    for r in rows
                ],
            }
        )
    return sorted(output, key=lambda x: (x.get("category", ""), x.get("metric", "")))


def _value(row: dict | None):
    return None if not row else row.get("value")


def build_dashboard() -> dict:
    documents = read_jsonl(table_path("documents"))
    events = read_jsonl(table_path("events"))
    entities = read_jsonl(table_path("entities"))
    sanctions = read_jsonl(table_path("sanctions"))
    statistics = read_jsonl(table_path("statistics"))
    watch_items = read_jsonl(table_path("watch_items"))
    source_runs = read_jsonl(table_path("source_runs"))

    coverage = summarize_coverage()
    quality = evaluate_consistency()
    latest = _latest_by_metric(statistics)

    private = latest.get("sujetos_obligados_sector_privado")
    public = latest.get("entidades_publicas_registradas")
    annual_total = latest.get("entidades_reportantes_total")
    private_date = _date_key(private or {})
    public_date = _date_key(public or {})
    if private and public and private_date and private_date == public_date:
        registered_total = float(private.get("value", 0)) + float(public.get("value", 0))
        registered_total_as_of = private_date
    else:
        registered_total = _value(annual_total)
        registered_total_as_of = _date_key(annual_total or {})

    document_type_counts = Counter(d.get("document_type", "UNKNOWN") for d in documents)
    sanction_amounts = [s.get("amount_uf") for s in sanctions if s.get("amount_uf")]

    kpis = {
        "registered_private_latest": _value(private),
        "registered_private_as_of": private_date,
        "registered_public_latest": _value(public),
        "registered_public_as_of": public_date,
        "registered_total_latest": registered_total,
        "registered_total_as_of": registered_total_as_of,
        "ros_latest": _value(latest.get("ros_recibidos")),
        "ros_latest_as_of": _date_key(latest.get("ros_recibidos") or {}),
        "roe_latest": _value(latest.get("roe_recibidos")),
        "roe_latest_as_of": _date_key(latest.get("roe_recibidos") or {}),
        "supervision_latest": _value(latest.get("acciones_supervision")),
        "supervision_latest_as_of": _date_key(latest.get("acciones_supervision") or {}),
        "fines_uf_latest": _value(latest.get("multas_sancionatorias_uf")),
        "fines_uf_latest_as_of": _date_key(latest.get("multas_sancionatorias_uf") or {}),
        "documents": len(documents),
        "events": len(events),
        "entities": len(entities),
        "sanctions": len(sanctions),
        "sanctions_total_uf_known": round(sum(sanction_amounts), 1) if sanction_amounts else 0,
        "statistics": len(statistics),
        "open_watch_items": sum(1 for w in watch_items if w.get("status") == "OPEN"),
        "sources_configured": coverage["sources"]["configured"],
        "sources_never_run": len(coverage["sources"]["never_run"]),
        "quality_status": quality["overall_status"],
    }

    trusted_statistics = sorted(
        statistics,
        key=lambda x: (_date_key(x), METHOD_RANK.get(x.get("capture_method", ""), 0)),
        reverse=True,
    )

    payload = {
        "version": "0.2.0",
        "generated_at": coverage["generated_at"],
        "disclaimer": DISCLAIMER,
        "kpis": kpis,
        "documents": sorted(documents, key=lambda x: x.get("document_date", "") or "", reverse=True)[:500],
        "documents_by_type": [{"name": k, "count": v} for k, v in document_type_counts.most_common()],
        "events": sorted(events, key=lambda x: x.get("event_date", "") or "", reverse=True)[:500],
        "entities": sorted(entities, key=lambda x: (x.get("sector", ""), x.get("name", "")))[:1000],
        "sanctions": sorted(sanctions, key=lambda x: x.get("resolution_date", "") or "", reverse=True)[:500],
        "statistics": trusted_statistics[:1000],
        "statistics_latest": latest,
        "statistics_series": _series(statistics),
        "watch_items": sorted(watch_items, key=lambda x: (x.get("status") == "OPEN", x.get("last_seen", "") or ""), reverse=True)[:200],
        "source_runs": sorted(source_runs, key=lambda x: x.get("finished_at", "") or "", reverse=True)[:300],
        "coverage": coverage,
        "quality": quality,
        "improvement_backlog": IMPROVEMENT_BACKLOG,
        "question_catalog": QUESTION_CATALOG,
    }

    out = DOCS_DIR / "data" / "dashboard.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload
