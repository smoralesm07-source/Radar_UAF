from __future__ import annotations

import re

from bs4 import BeautifulSoup

from .models import Document, Entity, Event, Sanction, Statistic, WatchItem, stable_id
from .utils import normalize_name, normalize_ws, parse_uf_amounts, sha256_text

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
    """Fallback para páginas antiguas que incluían la cifra directamente en HTML.
    v0.2 privilegia el XLSX oficial y conserva esta función para compatibilidad histórica."""
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


def registry_result_to_records(result: dict) -> tuple[list[Document], list[Entity], list[Statistic]]:
    sector = result.get("sector", "private")
    as_of = result.get("as_of_date", "")
    download_url = result.get("download_url", "") or result.get("source_url", "")
    label = "sector privado" if sector == "private" else "sector público"
    document = Document(
        document_id=stable_id("DOC", "REGISTRO_UAF", sector, as_of or download_url),
        source_system="UAF",
        source_module="SUJETOS_OBLIGADOS",
        source_url=download_url,
        title=f"Registro de Entidades Reportantes UAF - {label} - corte {as_of or 'vigente'}",
        document_type="REGISTRO_UAF_XLSX",
        document_date=as_of,
        status="VIGENTE",
        content_hash=result.get("content_hash", ""),
        raw_text_excerpt=(
            f"Listado oficial UAF con {result.get('listed_count', 0)} filas publicadas y "
            f"{result.get('unique_rut_count', 0)} RUT únicos."
        ),
    )

    entities: list[Entity] = []
    for row in result.get("rows", []):
        rut = row.get("rut", "")
        name = row.get("name", "") or rut
        if not rut:
            continue
        entities.append(
            Entity(
                entity_id=stable_id("ENT", "RUT", rut),
                entity_type="SUJETO_OBLIGADO" if sector == "private" else "ORGANISMO_PUBLICO",
                name=name,
                normalized_name=normalize_name(name),
                rut=rut,
                sector="PRIVADO" if sector == "private" else "PUBLICO",
                activity=row.get("activity", ""),
                source_document_id=document.document_id,
                confidence=1.0,
            )
        )

    if sector == "private":
        metric_listed = "sujetos_obligados_sector_privado"
        metric_unique = "sujetos_obligados_sector_privado_rut_unicos"
    else:
        metric_listed = "entidades_publicas_registradas"
        metric_unique = "entidades_publicas_rut_unicos"

    statistics = [
        Statistic(
            statistic_id=stable_id("STAT", "UAF_REGISTRY", metric_listed, as_of),
            metric=metric_listed,
            category="SUJETOS_OBLIGADOS",
            value=float(result.get("listed_count", 0)),
            unit="registros vigentes",
            as_of_date=as_of,
            source_url=download_url,
            capture_method="UAF_REGISTRY_XLSX",
            confidence=1.0,
        ),
        Statistic(
            statistic_id=stable_id("STAT", "UAF_REGISTRY", metric_unique, as_of),
            metric=metric_unique,
            category="SUJETOS_OBLIGADOS",
            value=float(result.get("unique_rut_count", 0)),
            unit="RUT únicos",
            as_of_date=as_of,
            source_url=download_url,
            capture_method="UAF_REGISTRY_XLSX",
            confidence=1.0,
        ),
    ]
    return [document], entities, statistics


def parse_sanciones_table(html: str, source_url: str) -> list[Sanction]:
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


def _es_number(raw: str) -> float:
    cleaned = re.sub(r"[^0-9,\.]", "", raw or "")
    if not cleaned:
        return 0.0
    if "." in cleaned and "," not in cleaned:
        cleaned = cleaned.replace(".", "")
    elif "," in cleaned:
        cleaned = cleaned.replace(".", "").replace(",", ".")
    try:
        return float(cleaned)
    except ValueError:
        return 0.0


def parse_statistical_report(report: dict, full_text: str) -> tuple[list[Document], list[Statistic]]:
    """Materializa indicadores clave del último Informe Estadístico anual de la UAF.
    Las series completas 2021-2025 se cargan desde config/official_statistics_2025.json;
    este extractor en vivo valida y actualiza los valores del último año directamente desde PDF."""
    year = int(report.get("report_year") or 0)
    url = report.get("report_url", "") or report.get("source_url", "")
    text = normalize_ws(full_text)
    document = Document(
        document_id=stable_id("DOC", "UAF_INFORME_ESTADISTICO", year or url),
        source_system="UAF",
        source_module="ESTADISTICAS",
        source_url=url,
        title=f"Informe Estadístico UAF {year}" if year else "Informe Estadístico UAF",
        document_type="INFORME_ESTADISTICO",
        document_date=f"{year}-12-31" if year else "",
        status="VIGENTE",
        content_hash=report.get("content_hash", ""),
        raw_text_excerpt=report.get("text_excerpt", ""),
    )
    if not year or not text:
        return [document], []

    patterns = {
        "entidades_reportantes_total": [
            rf"Al 31 de diciembre de {year},\s*([0-9\.]+)\s+personas naturales y jurídicas se encuentran inscritas",
            rf"Registro de Entidades Reportantes.{0,100}?{year}.{0,100}?([0-9\.]+)\s+personas naturales y jurídicas inscritas",
        ],
        "sujetos_obligados_sector_privado": [rf"De estas,\s*([0-9\.]+)\s+pertenecen a las 55 actividades económicas"],
        "entidades_publicas_registradas": [rf"y\s*([0-9\.]+)\s+son entidades públicas"],
        "ros_recibidos": [rf"durante el año {year} la UAF recibió un total de\s*([0-9\.]+)\s+ROS"],
        "roe_recibidos": [rf"Durante el {year}, la UAF recibió\s*([0-9\.]+)\s+ROE"],
        "acciones_supervision": [rf"en {year}, la UAF realizó\s*([0-9\.]+)\s+acciones de supervisión"],
        "procesos_sancionatorios_finalizados": [rf"durante el {year} la UAF finalizó.{0,100}?([0-9\.]+)\s+procesos sancionatorios"],
        "multas_sancionatorias_uf": [rf"multas a beneficio fiscal.{0,120}?ascendieron a UF\s*([0-9\.]+)"],
        "personas_informadas_en_ros": [rf"ROS recibidos en {year}.{0,120}?incluyeron información de\s*([0-9\.]+)\s+personas"],
        "ros_con_indicios_laft": [rf"información de\s*([0-9\.]+)\s+ROS, cuyos respectivos Informes de Inteligencia"],
    }
    categories = {
        "entidades_reportantes_total": "SUJETOS_OBLIGADOS",
        "sujetos_obligados_sector_privado": "SUJETOS_OBLIGADOS",
        "entidades_publicas_registradas": "SUJETOS_OBLIGADOS",
        "ros_recibidos": "INTELIGENCIA_FINANCIERA",
        "roe_recibidos": "INTELIGENCIA_FINANCIERA",
        "acciones_supervision": "SUPERVISION",
        "procesos_sancionatorios_finalizados": "SANCIONES",
        "multas_sancionatorias_uf": "SANCIONES",
        "personas_informadas_en_ros": "INTELIGENCIA_FINANCIERA",
        "ros_con_indicios_laft": "INTELIGENCIA_FINANCIERA",
    }
    units = {
        "entidades_reportantes_total": "personas y entidades",
        "sujetos_obligados_sector_privado": "entidades",
        "entidades_publicas_registradas": "entidades",
        "ros_recibidos": "reportes",
        "roe_recibidos": "reportes",
        "acciones_supervision": "acciones",
        "procesos_sancionatorios_finalizados": "procesos",
        "multas_sancionatorias_uf": "UF",
        "personas_informadas_en_ros": "personas",
        "ros_con_indicios_laft": "reportes",
    }

    statistics: list[Statistic] = []
    for metric, candidates in patterns.items():
        value = None
        for pattern in candidates:
            match = re.search(pattern, text, flags=re.IGNORECASE)
            if match:
                value = _es_number(match.group(1))
                break
        if value is None:
            continue
        statistics.append(
            Statistic(
                statistic_id=stable_id("STAT", "UAF_ANNUAL", metric, year),
                metric=metric,
                category=categories[metric],
                value=value,
                unit=units[metric],
                period=str(year),
                as_of_date=f"{year}-12-31",
                source_url=url,
                capture_method="LIVE_OFFICIAL_UAF_REPORT",
                confidence=1.0,
            )
        )
    return [document], statistics


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
