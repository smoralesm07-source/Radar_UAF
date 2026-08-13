from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from io import BytesIO
from urllib.parse import urljoin

import pandas as pd
import requests
from bs4 import BeautifulSoup
from pypdf import PdfReader
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from .config import DEFAULT_HEADERS, Source
from .utils import normalize_ws, official_or_open_data_url, parse_rut, sha256_text


@dataclass
class PageResult:
    source_id: str
    source_url: str
    status_code: int | None
    fetched_at: str
    content_hash: str = ""
    title: str = ""
    text_excerpt: str = ""
    links: list[dict] = field(default_factory=list)
    error: str = ""

    def to_dict(self) -> dict:
        return self.__dict__.copy()


class HTTPClient:
    """Cliente HTTP conservador para fuentes UAF / datos.gob.cl, con reintentos ante
    cortes transitorios y encabezados que identifican el proyecto como recolector OSINT."""

    def __init__(self, timeout: int = 35):
        self.session = requests.Session()
        self.session.headers.update(DEFAULT_HEADERS)
        retry = Retry(
            total=3,
            connect=3,
            read=3,
            status=3,
            backoff_factor=0.8,
            status_forcelist=(429, 500, 502, 503, 504),
            allowed_methods=frozenset(["GET"]),
            respect_retry_after_header=True,
            raise_on_status=False,
        )
        adapter = HTTPAdapter(max_retries=retry, pool_connections=8, pool_maxsize=8)
        self.session.mount("https://", adapter)
        self.session.mount("http://", adapter)
        self.timeout = timeout

    def get(self, url: str) -> requests.Response:
        response = self.session.get(url, timeout=self.timeout, allow_redirects=True)
        response.raise_for_status()
        return response


def collect_page(client: HTTPClient, source: Source) -> tuple[PageResult, str]:
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    try:
        response = client.get(source.url)
        html = response.text
        soup = BeautifulSoup(html, "lxml")
        title = normalize_ws(soup.title.get_text(" ", strip=True) if soup.title else source.name)
        links = []
        seen = set()
        for a in soup.find_all("a", href=True):
            href = urljoin(response.url, a.get("href", ""))
            if not official_or_open_data_url(href) or href in seen:
                continue
            seen.add(href)
            links.append({"url": href, "text": normalize_ws(a.get_text(" ", strip=True))[:250]})
            if len(links) >= source.max_items:
                break
        return (
            PageResult(
                source.id,
                response.url,
                response.status_code,
                now,
                sha256_text(html),
                title,
                normalize_ws(soup.get_text(" ", strip=True))[:3000],
                links,
            ),
            html,
        )
    except Exception as exc:
        return PageResult(source.id, source.url, None, now, error=f"{type(exc).__name__}: {exc}"), ""


def discover_downloads(html: str, base_url: str) -> list[dict]:
    """Descubre adjuntos publicados por la UAF preservando texto y contexto del bloque.
    Esto permite seguir enlaces aunque el CMS cambie el nombre físico del archivo."""
    soup = BeautifulSoup(html or "", "lxml")
    downloads: list[dict] = []
    seen: set[str] = set()
    for a in soup.find_all("a", href=True):
        href = urljoin(base_url, a.get("href", ""))
        lower = href.lower().split("?", 1)[0]
        if not lower.endswith((".xlsx", ".xls", ".csv", ".pdf")) or href in seen:
            continue
        seen.add(href)
        parent = a.find_parent(["article", "li", "div", "section"])
        context = normalize_ws(parent.get_text(" ", strip=True) if parent else a.get_text(" ", strip=True))[:800]
        downloads.append({"url": href, "text": normalize_ws(a.get_text(" ", strip=True)), "context": context})
    return downloads


def _cutoff_from_registry_page(html: str) -> str:
    text = normalize_ws(BeautifulSoup(html or "", "lxml").get_text(" ", strip=True))
    matches = re.findall(r"inscrit[oa]s?.{0,120}?al\s+(\d{1,2})/(\d{1,2})/(\d{4})", text, flags=re.IGNORECASE)
    if not matches:
        matches = re.findall(r"al\s+(\d{1,2})/(\d{1,2})/(\d{4})", text, flags=re.IGNORECASE)
    dates = []
    for d, m, y in matches:
        try:
            dates.append((int(y), int(m), int(d)))
        except ValueError:
            continue
    if not dates:
        return ""
    y, m, d = max(dates)
    return f"{y:04d}-{m:02d}-{d:02d}"


def _registry_candidate(downloads: list[dict], sector: str) -> dict | None:
    xlsx = [d for d in downloads if d["url"].lower().split("?", 1)[0].endswith((".xlsx", ".xls"))]
    if not xlsx:
        return None
    scored = []
    for item in xlsx:
        haystack = f"{item.get('context', '')} {item.get('url', '')}".lower()
        score = 0
        if "buscador" in haystack:
            score += 4
        if "inscrit" in haystack:
            score += 3
        if sector == "private":
            if "sujeto" in haystack or "obligad" in haystack:
                score += 5
            if "institucion" in haystack or "municip" in haystack:
                score -= 6
        else:
            if "institucion" in haystack or "municip" in haystack or "public" in haystack:
                score += 5
            if "sujeto" in haystack and "obligad" in haystack:
                score -= 3
        scored.append((score, item))
    return max(scored, key=lambda x: x[0])[1]


def collect_registry_workbook(client: HTTPClient, source: Source, html: str, page_url: str, sector: str) -> dict:
    """Descarga el XLSX vigente enlazado por la UAF y reconstruye el registro por RUT.
    Conserva dos conteos: filas listadas y RUT únicos. El primero replica el universo publicado;
    el segundo sirve para el futuro Entity Hub y permite detectar duplicidad por actividad."""
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    downloads = discover_downloads(html, page_url)
    candidate = _registry_candidate(downloads, sector)
    result = {
        "source_id": source.id,
        "source_url": page_url,
        "fetched_at": now,
        "sector": sector,
        "as_of_date": _cutoff_from_registry_page(html),
        "download_url": candidate.get("url", "") if candidate else "",
        "listed_count": 0,
        "unique_rut_count": 0,
        "rows": [],
        "error": "",
    }
    if not candidate:
        result["error"] = "No se encontro XLSX de registro en la pagina UAF"
        return result
    try:
        response = client.get(candidate["url"])
        book = pd.ExcelFile(BytesIO(response.content), engine="openpyxl")
        raw_rows: list[dict] = []
        sequence_numbers: list[int] = []
        for sheet in book.sheet_names:
            frame = pd.read_excel(book, sheet_name=sheet, header=None, dtype=str)
            for _, series in frame.iterrows():
                cells = []
                for value in series.tolist():
                    if value is None or str(value).strip().lower() == "nan":
                        cells.append("")
                    else:
                        cells.append(normalize_ws(str(value)))
                joined = " | ".join(c for c in cells if c)
                rut = parse_rut(joined)
                if not rut:
                    continue
                rut_idx = next((i for i, c in enumerate(cells) if parse_rut(c)), -1)
                seq = None
                for c in cells[: max(rut_idx, 1)]:
                    if re.fullmatch(r"\d{1,6}(?:\.0)?", c):
                        try:
                            seq = int(float(c))
                            break
                        except ValueError:
                            pass
                if seq:
                    sequence_numbers.append(seq)
                candidates = []
                for i, c in enumerate(cells):
                    if not c or i == rut_idx or parse_rut(c) or re.fullmatch(r"\d+(?:\.0)?", c):
                        continue
                    if c.upper() in {"RUT", "NOMBRE", "RAZON SOCIAL", "RAZÓN SOCIAL", "ACTIVIDAD", "SECTOR", "N°", "Nº"}:
                        continue
                    if len(c) >= 3:
                        candidates.append((i, c))
                after = [(i, c) for i, c in candidates if i > rut_idx]
                ordered = after if after else candidates
                name = ordered[0][1] if ordered else ""
                activity = ordered[1][1] if len(ordered) > 1 else ""
                raw_rows.append({"rut": rut, "name": name, "activity": activity, "sheet": sheet, "sequence": seq})

        dedup_rows: dict[tuple, dict] = {}
        by_rut: dict[str, dict] = {}
        for row in raw_rows:
            dedup_rows[(row["rut"], row["name"], row["activity"])] = row
            current = by_rut.setdefault(row["rut"], {"rut": row["rut"], "name": row["name"], "activities": set()})
            if not current["name"] and row["name"]:
                current["name"] = row["name"]
            if row["activity"]:
                current["activities"].add(row["activity"])
        rows = [
            {"rut": r["rut"], "name": r["name"], "activity": " | ".join(sorted(r["activities"]))}
            for r in by_rut.values()
        ]
        listed_count = max(sequence_numbers) if sequence_numbers else len(dedup_rows)
        result.update(
            {
                "listed_count": int(listed_count),
                "unique_rut_count": len(rows),
                "rows": rows[: source.max_items],
                "sheet_names": book.sheet_names,
                "workbook_bytes": len(response.content),
                "content_hash": sha256_text(response.content.hex()),
            }
        )
    except Exception as exc:
        result["error"] = f"{type(exc).__name__}: {exc}"
    return result


def _year_from_text(text: str) -> int:
    years = [int(y) for y in re.findall(r"\b(20\d{2})\b", text or "")]
    return max(years) if years else 0


def collect_statistics_report(client: HTTPClient, source: Source, html: str, page_url: str) -> tuple[dict, str]:
    """Descubre y descarga el Informe Estadístico anual más reciente publicado por la UAF.
    Extrae el texto del PDF con pypdf para que extract.py materialice indicadores verificables."""
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    downloads = discover_downloads(html, page_url)
    pdfs = []
    for item in downloads:
        if not item["url"].lower().split("?", 1)[0].endswith(".pdf"):
            continue
        haystack = f"{item.get('context', '')} {item.get('url', '')}".lower()
        if "informe" in haystack and "estad" in haystack and "serie" not in haystack:
            pdfs.append((_year_from_text(haystack), item))
    result = {
        "source_id": source.id,
        "source_url": page_url,
        "fetched_at": now,
        "report_url": "",
        "report_year": 0,
        "page_count": 0,
        "error": "",
    }
    if not pdfs:
        result["error"] = "No se encontro Informe Estadistico PDF en la pagina UAF"
        return result, ""
    year, candidate = max(pdfs, key=lambda x: x[0])
    try:
        response = client.get(candidate["url"])
        reader = PdfReader(BytesIO(response.content))
        page_texts = [(page.extract_text() or "") for page in reader.pages]
        full_text = "\n".join(page_texts)
        result.update(
            {
                "report_url": response.url,
                "report_year": year or _year_from_text(full_text),
                "page_count": len(reader.pages),
                "content_hash": sha256_text(response.content.hex()),
                "text_excerpt": normalize_ws(full_text)[:3000],
            }
        )
        return result, full_text
    except Exception as exc:
        result["error"] = f"{type(exc).__name__}: {exc}"
        return result, ""


def collect_ckan_datasets(client: HTTPClient, source: Source) -> tuple[dict, str]:
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    try:
        response = client.get(source.url)
        payload = response.json()
        datasets = (payload.get("result") or {}).get("results", [])
        return {
            "source_id": source.id,
            "source_url": response.url,
            "fetched_at": now,
            "status_code": response.status_code,
            "dataset_count": len(datasets),
            "datasets": [
                {
                    "name": d.get("name", ""),
                    "title": d.get("title", ""),
                    "notes": normalize_ws((d.get("notes") or "")[:500]),
                    "metadata_modified": d.get("metadata_modified", ""),
                    "num_resources": len(d.get("resources") or []),
                    "resource_formats": sorted({r.get("format", "") for r in (d.get("resources") or []) if r.get("format")}),
                    "url": f"https://datos.gob.cl/dataset/{d.get('name', '')}" if d.get("name") else "",
                }
                for d in datasets[: source.max_items]
            ],
        }, response.text
    except Exception as exc:
        return {
            "source_id": source.id,
            "source_url": source.url,
            "fetched_at": now,
            "error": f"{type(exc).__name__}: {exc}",
            "datasets": [],
        }, ""
