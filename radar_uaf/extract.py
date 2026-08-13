from __future__ import annotations

import re

from bs4 import BeautifulSoup

from .models import Document, Entity, Event, Sanction, Statistic, WatchItem, stable_id, utcnow_iso
from .utils import normalize_name, normalize_ws, parse_rut, parse_uf_amounts, sha256_text

CIRCULAR_RE = re.compile(r"circular\s+(?:uaf\s+)?n?°?\s*(\d+)", re.IGNORECASE)
DATE_RE = re.compile(r"\b(\d{1,2})[-/](\d{1,2})[-/](\d{4})\b")
COUNT_RE = re.compile(r"([0-9]{1,3}(?:[.,][0-9]{3})+|[0-9]{2,6})\s*(entidades|personas|sujetos obligados)", re.IGNORECASE)
STATUS_WORDS = {"VIGENTE": "VIGENTE", "DEROGADA": "DEROGADA", "DEROGADO": "DEROGADA", "SIN VIGENCIA": "DEROGADA"}


def _iso_date(day: str, month: str, year: str) -> str:
    try:
        return f"{int(year):04d}-{int(month):02d}-{int(day):02d}"
    except Exception:
        return ""


def first_date(text: str) -> str:
    match = DATE_RE.search(text or "")
    if not match:
        return ""
    return _iso_date(*match.groups())


def parse_normativa_index(html: str, source_url: str) -> tuple[list[Document], list[WatchItem]]:
    """Extrae circulares/normas listadas en la pagina de normativa UAF. Cada fila o bloque
    de texto que menciona 'Circular N°X' se registra como Document; si el bloque no declara
    explicitamente su estado se marca UNKNOWN para evitar inferir vigencia sin evidencia."""
    soup = BeautifulSoup(html or "", "lxml")
    documents: list[Document] = []
    watch: list[WatchItem] = []
    blocks = soup.find_all(["tr", "li", "p", "article"]) or [soup]
    seen_numbers: set[str] = set()
    for block in blocks:
        text = normalize_ws(block.get_text(" ", strip=True))
        match = CIRCULAR_RE.search(text)
        if not match:
            continue
        number = match.group(1)
        if number in seen_numbers:
            continue
        seen_numbers.add(number)
        status = "UNKNOWN"
        for word, mapped in STATUS_WORDS.items():
            if word in text.upper():
                status = mapped
                break
        link = block.find("a", href=True)
        doc_url = link["href"] if link and link.get("href", "").startswith("http") else source_url
        doc = Document(
            document_id=stable_id("DOC", "CIRCULAR", number),
            source_system="UAF",
            source_module="NORMATIVA",
            source_url=doc_url,
            title=f"Circular UAF N°{number}",
            document_type="CIRCULAR",
            document_number=number,
            document_date=first_date(text),
            status=status,
            content_hash=sha256_text(text),
            raw_text_excerpt=text[:600],
        )
        documents.append(doc)
        if status == "UNKNOWN":
            watch.append(
                WatchItem(
                    watch_id=stable_id("WATCH", "NORMATIVA_ESTADO", number),
                    source_id="uaf_circulares",
                    watch_type="NORMATIVA_CAMBIO",
                    title=f"Confirmar estado de vigencia de Circular UAF N°{number}",
                    source_url=doc_url,
                    stage="WATCH",
                )
            )
    return documents, watch


def parse_registry_snapshot(html: str, source_url: str) -> list[Statistic]:
    """Busca cifras agregadas del Registro de Entidades Reportantes en el texto de la pagina
    (p.ej. '8.970 entidades'). No intenta reconstruir el listado individual de inscritos desde
    esta vista resumen; eso queda para una extraccion tabular dedicada en una iteracion futura."""
    soup = BeautifulSoup(html or "", "lxml")
    text = normalize_ws(soup.get_text(" ", strip=True))
    stats: list[Statistic] = []
    for match in COUNT_RE.finditer(text):
        raw_value, unit_word = match.groups()
        digits = re.sub(r"[.,]", "", raw_value)
        try:
            value = float(digits)
        except ValueError:
            continue
        if value < 10 or value > 200000:
            continue
        stats.append(
            Statistic(
                statistic_id=stable_id("STAT", "REGISTRY", source_url, digits),
                metric="sujetos_obligados_registrados",
                category="SUJETOS_OBLIGADOS",
                value=value,
                unit=unit_word.lower(),
                as_of_date=first_date(text),
                source_url=source_url,
                capture_method="LIVE_SCRAPE",
                confidence=0.55,
            )
        )
    return stats[:5]


def parse_sanciones_table(html: str, source_url: str) -> list[Sanction]:
    """Extrae filas de tablas de sanciones ejecutoriadas. Tolera distintas estructuras de
    tabla; si una fila no trae al menos un nombre y una fecha reconocible, se descarta."""
    soup = BeautifulSoup(html or "", "lxml")
    sanctions: list[Sanction] = []
    rows = soup.find_all("tr")
    for row in rows:
        cells = [normalize_ws(td.get_text(" ", strip=True)) for td in row.find_all(["td", "th"])]
        if len(cells) < 2:
            continue
        row_text = " | ".join(cells)
        date = first_date(row_text)
        name_candidates = [c for c in cells if len(c) > 3 and not DATE_RE.search(c) and not re.fullmatch(r"[\d\.\-\s]+", c)]
        if not name_candidates:
            continue
        name = name_candidates[0]
        if name.strip().upper() in {"FECHA", "NOMBRE", "RESOLUCION", "RESOLUCIÓN", "ENTIDAD", "MONTO"}:
            continue
        amounts = parse_uf_amounts(row_text)
        resolution_match = re.search(r"\b(?:N°|N|Res\.?)\s*([0-9]{1,6}(?:/[0-9]{2,4})?)\b", row_text, re.IGNORECASE)
        entity_id = stable_id("ENT", "SANCIONADO", normalize_name(name))
        sanctions.append(
            Sanction(
                sanction_id=stable_id("SANC", source_url, name, date, resolution_match.group(1) if resolution_match else ""),
                document_id=stable_id("DOC", "SANCION_INDEX", source_url),
                entity_id=entity_id,
                entity_name=name,
                resolution_number=resolution_match.group(1) if resolution_match else "",
                resolution_date=date,
                amount_uf=amounts[0] if amounts else None,
                reason_summary=row_text[:300],
                source_url=source_url,
            )
        )
    return sanctions


def parse_ckan_statistics(ckan_result: dict) -> tuple[list[Document], list[Statistic]]:
    documents: list[Document] = []
    statistics: list[Statistic] = []
    for dataset in ckan_result.get("datasets", []):
        doc = Document(
            document_id=stable_id("DOC", "CKAN_DATASET", dataset.get("name", "")),
            source_system="DATOS_GOB_CL",
            source_module="DATOS_ABIERTOS",
            source_url=dataset.get("url", ""),
            title=dataset.get("title", ""),
            document_type="DATASET",
            document_date=dataset.get("metadata_modified", "")[:10],
            status="VIGENTE",
            raw_text_excerpt=dataset.get("notes", ""),
        )
        documents.append(doc)
        statistics.append(
            Statistic(
                statistic_id=stable_id("STAT", "CKAN_RESOURCES", dataset.get("name", "")),
                metric="dataset_recursos_publicados",
                category="DATOS_ABIERTOS",
                value=float(dataset.get("num_resources", 0)),
                unit="recursos",
                as_of_date=dataset.get("metadata_modified", "")[:10],
                source_url=dataset.get("url", ""),
                capture_method="CKAN_API",
                confidence=0.85,
            )
        )
    return documents, statistics


def parse_news_index(html: str, index_url: str) -> list[dict]:
    soup = BeautifulSoup(html or "", "lxml")
    candidates = []
    seen = set()
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if "noticia-detalle" not in href:
            continue
        if href in seen:
            continue
        seen.add(href)
        candidates.append({"url": href, "text": normalize_ws(a.get_text(" ", strip=True))})
    return candidates


def seed_fact_to_records(fact: dict) -> tuple[Document | None, Statistic | None, Event | None]:
    """Traduce un hecho semilla (config/seed_facts.json) verificado por busqueda OSINT a las
    tablas Document/Statistic/Event, preservando su procedencia distinta a un scrape en vivo."""
    document = Document(
        document_id=stable_id("DOC", "SEED", fact["fact_id"]),
        source_system="UAF" if "uaf.cl" in fact.get("source_url", "") else "OSINT_TERCERO",
        source_module=fact.get("category", "GENERAL"),
        source_url=fact.get("source_url", ""),
        title=fact.get("title", ""),
        document_type="SEED_FACT",
        document_date=fact.get("publication_date") or fact.get("as_of_date") or fact.get("effective_date") or "",
        status="SEED_PENDING_LIVE_CONFIRMATION",
        raw_text_excerpt=fact.get("description", "")[:800],
    )
    statistic = None
    if "metric" in fact and "value" in fact:
        statistic = Statistic(
            statistic_id=stable_id("STAT", "SEED", fact["fact_id"]),
            metric=fact["metric"],
            category=fact.get("category", "GENERAL"),
            value=float(fact["value"]),
            period=fact.get("period", ""),
            as_of_date=fact.get("as_of_date", ""),
            source_url=fact.get("source_url", ""),
            capture_method="SEED_OSINT_SUMMARY",
            confidence=float(fact.get("confidence", 0.5)),
        )
    event = Event(
        event_id=stable_id("EVT", "SEED", fact["fact_id"]),
        document_id=document.document_id,
        event_type="SEED_FACT_CAPTURADO",
        event_date=document.document_date,
        title=fact.get("title", ""),
        source_url=fact.get("source_url", ""),
        source_module=fact.get("category", "GENERAL"),
        status="SEED",
    )
    return document, statistic, event
