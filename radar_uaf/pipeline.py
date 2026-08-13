from __future__ import annotations

import argparse
import json
import time
from datetime import datetime, timezone

from .collectors import (
    HTTPClient,
    collect_ckan_datasets,
    collect_page,
    collect_registry_workbook,
    collect_statistics_report,
)
from .config import load_sources
from .dashboard import build_dashboard
from .extract import (
    parse_ckan_statistics,
    parse_news_index,
    parse_normativa_index,
    parse_registry_snapshot,
    parse_sanciones_table,
    parse_statistical_report,
    registry_result_to_records,
)
from .models import Document, Event, SourceRun, stable_id
from .seed import load_official_statistics_into_silver, load_seed_into_silver
from .storage import export_parquet, upsert_jsonl, write_snapshot
from .utils import normalize_name

REFERENCE_COLLECTORS = {"page_discovery", "sanctions_list", "search_discovery"}
REGISTRY_COLLECTORS = {"registry_workbook_private", "registry_workbook_public"}


def iso_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _build_entities_from_sanctions(sanctions: list[dict]) -> list[dict]:
    entities = {}
    for row in sanctions:
        eid = row.get("entity_id")
        name = row.get("entity_name", "")
        if not eid or not name:
            continue
        entities[eid] = {
            "entity_id": eid,
            "entity_type": "SANCIONADO_ORGANIZACION",
            "name": name,
            "normalized_name": normalize_name(name),
            "rut": "",
            "sector": "",
            "activity": "",
            "source_document_id": row.get("document_id", ""),
            "confidence": 0.5,
        }
    return list(entities.values())


def _registry_snapshot_payload(page: dict, result: dict) -> dict:
    registry = {k: v for k, v in result.items() if k != "rows"}
    registry["sample_rows"] = (result.get("rows") or [])[:20]
    return {"page": page, "registry": registry}


def run(source_filter: str | None = None, skip_network: bool = False) -> dict:
    started = iso_now()
    client = HTTPClient()
    runs: list[dict] = []
    all_sanctions: list[dict] = []
    totals = {
        "new_documents": 0,
        "updated_documents": 0,
        "new_entities": 0,
        "new_sanctions": 0,
        "new_statistics": 0,
        "errors": 0,
    }

    # Series oficiales 2021-2025: base determinista. La lectura en vivo del PDF reemplaza
    # el mismo statistic_id cuando confirma el valor del último año.
    official_statistics = load_official_statistics_into_silver()

    if not skip_network:
        for source in load_sources():
            if source_filter and source.id != source_filter:
                continue
            run_started = iso_now()
            items_found = 0
            status = "OK"
            error = ""
            http_status = None
            content_hash = ""
            try:
                if source.collector == "ckan_datasets":
                    result, _ = collect_ckan_datasets(client, source)
                    write_snapshot(source.id, run_started[:10], result)
                    http_status = result.get("status_code")
                    error = result.get("error", "")
                    if error:
                        status = "ERROR"
                        totals["errors"] += 1
                    documents, statistics = parse_ckan_statistics(result)
                    items_found = len(documents)
                    i, u = upsert_jsonl("documents", [d.to_dict() for d in documents], "document_id")
                    totals["new_documents"] += i
                    totals["updated_documents"] += u
                    si, _ = upsert_jsonl("statistics", [s.to_dict() for s in statistics], "statistic_id")
                    totals["new_statistics"] += si
                else:
                    page, html = collect_page(client, source)
                    http_status = page.status_code
                    error = page.error
                    content_hash = page.content_hash
                    if page.error:
                        status = "ERROR"
                        totals["errors"] += 1

                    if source.collector in REGISTRY_COLLECTORS and html:
                        sector = "private" if source.collector == "registry_workbook_private" else "public"
                        result = collect_registry_workbook(client, source, html, page.source_url or source.url, sector)
                        write_snapshot(source.id, run_started[:10], _registry_snapshot_payload(page.to_dict(), result))
                        if result.get("error"):
                            status = "ERROR"
                            error = result["error"]
                            totals["errors"] += 1
                        if result.get("listed_count") or result.get("unique_rut_count"):
                            documents, entities, statistics = registry_result_to_records(result)
                            items_found = int(result.get("listed_count") or result.get("unique_rut_count") or 0)
                            i, u = upsert_jsonl("documents", [d.to_dict() for d in documents], "document_id")
                            totals["new_documents"] += i
                            totals["updated_documents"] += u
                            ei, _ = upsert_jsonl("entities", [e.to_dict() for e in entities], "entity_id")
                            totals["new_entities"] += ei
                            si, _ = upsert_jsonl("statistics", [s.to_dict() for s in statistics], "statistic_id")
                            totals["new_statistics"] += si
                    elif source.collector == "statistics_report_index" and html:
                        report, full_text = collect_statistics_report(client, source, html, page.source_url or source.url)
                        write_snapshot(source.id, run_started[:10], {"page": page.to_dict(), "report": report})
                        if report.get("error"):
                            status = "ERROR"
                            error = report["error"]
                            totals["errors"] += 1
                        documents, statistics = parse_statistical_report(report, full_text)
                        items_found = len(statistics)
                        i, u = upsert_jsonl("documents", [d.to_dict() for d in documents], "document_id")
                        totals["new_documents"] += i
                        totals["updated_documents"] += u
                        if statistics:
                            si, _ = upsert_jsonl("statistics", [s.to_dict() for s in statistics], "statistic_id")
                            totals["new_statistics"] += si
                    else:
                        write_snapshot(source.id, run_started[:10], page.to_dict())
                        if source.collector == "normativa_index" and html:
                            documents, watch = parse_normativa_index(html, page.source_url or source.url)
                            items_found = len(documents)
                            i, u = upsert_jsonl("documents", [d.to_dict() for d in documents], "document_id")
                            totals["new_documents"] += i
                            totals["updated_documents"] += u
                            upsert_jsonl("watch_items", [w.to_dict() for w in watch], "watch_id")
                        elif source.collector == "registry_snapshot" and html:
                            statistics = parse_registry_snapshot(html, page.source_url or source.url)
                            items_found = len(statistics)
                            si, _ = upsert_jsonl("statistics", [s.to_dict() for s in statistics], "statistic_id")
                            totals["new_statistics"] += si
                        elif source.collector == "sanciones_legacy" and html:
                            sanctions = parse_sanciones_table(html, page.source_url or source.url)
                            all_sanctions.extend(s.to_dict() for s in sanctions)
                            items_found = len(sanctions)
                            i, _ = upsert_jsonl("sanctions", [s.to_dict() for s in sanctions], "sanction_id")
                            totals["new_sanctions"] += i
                        elif source.collector == "news_index" and html:
                            articles = parse_news_index(html, page.source_url or source.url)
                            items_found = len(articles)
                            events = [
                                Event(
                                    event_id=stable_id("EVT", "UAF_NEWS", a["url"]),
                                    document_id="",
                                    event_type="NOTICIA",
                                    event_date="",
                                    title=a.get("text", "") or a["url"],
                                    source_url=a["url"],
                                    source_module="NOTICIAS",
                                ).to_dict()
                                for a in articles
                                if a.get("url")
                            ]
                            upsert_jsonl("events", events, "event_id")
                        elif source.collector in REFERENCE_COLLECTORS and html:
                            ref_doc = Document(
                                document_id=stable_id("DOC", "REFERENCE_PAGE", source.id),
                                source_system="UAF",
                                source_module=source.id.upper(),
                                source_url=page.source_url or source.url,
                                title=page.title or source.name,
                                document_type="PAGINA_REFERENCIA",
                                status="VIGENTE",
                                content_hash=content_hash,
                                raw_text_excerpt=page.text_excerpt,
                            )
                            items_found = 1
                            i, u = upsert_jsonl("documents", [ref_doc.to_dict()], "document_id")
                            totals["new_documents"] += i
                            totals["updated_documents"] += u
            except Exception as exc:
                status = "ERROR"
                error = f"{type(exc).__name__}: {exc}"
                totals["errors"] += 1

            runs.append(
                SourceRun(
                    run_id=stable_id("RUN", source.id, run_started),
                    source_id=source.id,
                    source_name=source.name,
                    source_url=source.url,
                    started_at=run_started,
                    finished_at=iso_now(),
                    status=status,
                    http_status=http_status,
                    content_hash=content_hash,
                    items_found=items_found,
                    error=error,
                ).to_dict()
            )
            time.sleep(0.2)
    else:
        runs.append(
            SourceRun(
                run_id=stable_id("RUN", "skip_network", started),
                source_id="ALL",
                source_name="Todas las fuentes",
                source_url="",
                started_at=started,
                finished_at=iso_now(),
                status="SKIPPED_NO_NETWORK",
                items_found=0,
                error="",
            ).to_dict()
        )

    if runs:
        upsert_jsonl("source_runs", runs, "run_id")

    # Las semillas se conservan como historia y evidencia auxiliar, nunca como encabezado vigente.
    seed_result = load_seed_into_silver()

    from .storage import read_jsonl, table_path

    sanction_entities = _build_entities_from_sanctions(read_jsonl(table_path("sanctions")))
    if sanction_entities:
        upsert_jsonl("entities", sanction_entities, "entity_id")

    parquet = export_parquet()
    dashboard = build_dashboard()

    return {
        "started_at": started,
        "totals": totals,
        "official_statistics": official_statistics,
        "seed": seed_result,
        "parquet": parquet,
        "dashboard_kpis": dashboard["kpis"],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Radar UAF - pipeline OSINT")
    parser.add_argument("--source")
    parser.add_argument("--skip-network", action="store_true")
    args = parser.parse_args()
    print(json.dumps(run(args.source, args.skip_network), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
