from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone

from .config import load_sources
from .storage import read_jsonl, table_path


def _min(values: list[str]) -> str:
    vals = [x for x in values if x]
    return min(vals) if vals else ""


def _max(values: list[str]) -> str:
    vals = [x for x in values if x]
    return max(vals) if vals else ""


def summarize_coverage() -> dict:
    documents = read_jsonl(table_path("documents"))
    sanctions = read_jsonl(table_path("sanctions"))
    statistics = read_jsonl(table_path("statistics"))
    runs = read_jsonl(table_path("source_runs"))
    sources = load_sources()

    dates = [d.get("document_date", "") for d in documents]
    module_counts = Counter(d.get("source_module", "UNKNOWN") for d in documents)
    type_counts = Counter(d.get("document_type", "UNKNOWN") for d in documents)

    source_latest = {}
    for row in sorted(runs, key=lambda x: x.get("finished_at", "")):
        sid = row.get("source_id", "")
        if sid:
            source_latest[sid] = {
                "status": row.get("status", ""),
                "finished_at": row.get("finished_at", ""),
                "error": row.get("error", ""),
                "items_found": row.get("items_found", 0),
            }

    covered_source_ids = set(source_latest)
    configured_source_ids = {s.id for s in sources}
    never_run = sorted(configured_source_ids - covered_source_ids)

    return {
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "warning": "La cobertura depende de que las rutas configuradas sigan vigentes en el sitio de la UAF; varias fuentes usan URLs legadas (.aspx) que deben reconfirmarse periodicamente.",
        "documents": {
            "count": len(documents),
            "oldest_date": _min(dates),
            "newest_date": _max(dates),
            "by_module": [{"name": k, "count": v} for k, v in module_counts.most_common()],
            "by_type": [{"name": k, "count": v} for k, v in type_counts.most_common()],
        },
        "sanctions": {
            "count": len(sanctions),
            "with_amount": sum(1 for s in sanctions if s.get("amount_uf")),
        },
        "statistics": {
            "count": len(statistics),
            "by_capture_method": [
                {"name": k, "count": v}
                for k, v in Counter(s.get("capture_method", "UNKNOWN") for s in statistics).most_common()
            ],
        },
        "sources": {
            "configured": len(configured_source_ids),
            "with_at_least_one_run": len(covered_source_ids & configured_source_ids),
            "never_run": never_run,
            "latest_run_by_source": source_latest,
        },
    }
