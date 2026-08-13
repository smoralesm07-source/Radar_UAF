from __future__ import annotations

import hashlib
import re
import unicodedata
from pathlib import Path
from urllib.parse import urlparse


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", errors="ignore")).hexdigest()


def normalize_ws(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def normalize_name(text: str) -> str:
    value = unicodedata.normalize("NFKD", text or "")
    value = "".join(ch for ch in value if not unicodedata.combining(ch))
    value = re.sub(r"[^A-Za-z0-9 ]+", " ", value.upper())
    value = re.sub(r"\s+", " ", value).strip()
    replacements = {" S A ": " SA ", " S P A ": " SPA ", " LTDA ": " LIMITADA "}
    padded = f" {value} "
    for old, new in replacements.items():
        padded = padded.replace(old, new)
    return padded.strip()


def parse_uf_amounts(text: str) -> list[float]:
    """Extrae montos expresados en UF (Unidad de Fomento), unidad habitual de las sanciones UAF."""
    values: list[float] = []
    for raw in re.findall(r"([0-9][0-9\.]{0,9}(?:,[0-9]+)?)\s*UF\b", text or "", flags=re.IGNORECASE):
        normalized = raw.replace(".", "").replace(",", ".")
        try:
            values.append(float(normalized))
        except ValueError:
            continue
    return values


def parse_rut(text: str) -> str:
    match = re.search(r"\b(\d{1,2}\.?\d{3}\.?\d{3}-[0-9kK])\b", text or "")
    if not match:
        return ""
    return match.group(1).replace(".", "").upper()


def official_uaf_url(url: str) -> bool:
    try:
        host = urlparse(url).hostname or ""
        return host.endswith("uaf.cl")
    except Exception:
        return False


def official_or_open_data_url(url: str) -> bool:
    try:
        host = urlparse(url).hostname or ""
        return host.endswith("uaf.cl") or host.endswith("datos.gob.cl")
    except Exception:
        return False


def ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
