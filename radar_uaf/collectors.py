from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from .config import DEFAULT_HEADERS, Source
from .utils import normalize_ws, official_or_open_data_url, sha256_text


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
    """Descubrimiento generico de pagina: usado por page_discovery, normativa_index,
    registry_snapshot, sanctions_list, sanciones_legacy, news_index y search_discovery.
    La diferenciacion de contenido ocurre en extract.py sobre el HTML crudo devuelto."""
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


def collect_ckan_datasets(client: HTTPClient, source: Source) -> tuple[dict, str]:
    """Consume la API estandar CKAN de datos.gob.cl (package_search) para la organizacion
    UAF. Preferible al scraping HTML porque devuelve metadatos estructurados (recursos,
    formatos, fechas de actualizacion) directamente utilizables como Document/Statistic."""
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
