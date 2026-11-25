"""Automatic, licence-aware photo sourcing for Cinematic Skill scenes.

Uses the upstream Cinematic Skill Commons client and licence policy. Only Public Domain,
CC0, CC BY and CC BY-SA material is selected automatically; non-free / unclear rights
are never silently treated as reusable.
"""
from __future__ import annotations

import logging
import pathlib
import re
import sys
import time
import urllib.parse
import urllib.request

log = logging.getLogger("cinematic_assets")
MAX_DOWNLOAD_BYTES = 18 * 1024 * 1024
MIN_IMAGE_WIDTH = 500
UA = "script-to-video/1.0 (+https://github.com/AarushSrivatsa/EcommerceWebsite)"

_SKILL_SCRIPTS = (
    pathlib.Path(__file__).resolve().parents[1]
    / "vendor"
    / "cinematic_skill"
    / "skills"
    / "cinematic-film"
    / "scripts"
)
if str(_SKILL_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SKILL_SCRIPTS))

# Reuse the actual upstream search, metadata extraction and allowed-licence expression.
from fetch_commons import FREE, IIPROP, api, info  # noqa: E402


def _candidate_score(item: dict, query: str) -> float:
    title = str(item.get("title") or "").lower()
    description = str(item.get("desc") or "").lower()
    terms = [word for word in re.findall(r"[a-z0-9]{3,}", query.lower()) if word not in {"the", "and", "for", "from", "with"}]
    haystack = f"{title} {description}"
    overlap = sum(1 for word in set(terms) if word in haystack)
    width, height = int(item.get("w") or 0), int(item.get("h") or 0)
    if width < MIN_IMAGE_WIDTH or height < 300:
        return -1000
    ratio = width / max(height, 1)
    if overlap == 0:
        return -1000
    score = overlap * 3.0 + min(width * height / 1_000_000, 8.0)
    if ratio < 0.45 or ratio > 2.4:
        score -= 1.5
    if "svg" in str(item.get("mime") or "").lower():
        return -1000
    return score


def _download(url: str, destination: pathlib.Path) -> bool:
    """Download at most 18 MB, retrying Commons throttling responses."""
    import urllib.error
    request = urllib.request.Request(url, headers={"User-Agent": UA})
    for attempt in range(4):
        try:
            with urllib.request.urlopen(request, timeout=50) as response:
                declared = response.headers.get("Content-Length")
                if declared and int(declared) > MAX_DOWNLOAD_BYTES:
                    return False
                data = response.read(MAX_DOWNLOAD_BYTES + 1)
            if not data or len(data) > MAX_DOWNLOAD_BYTES:
                return False
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(data)
            return True
        except urllib.error.HTTPError as exc:
            if exc.code in (429, 503) and attempt < 3:
                time.sleep(3 * (attempt + 1))
                continue
            log.info("Commons image download refused (%s): HTTP %s", url, exc.code)
            break
        except Exception as exc:
            log.info("Commons image download failed (%s): %s", url, exc)
            break
    destination.unlink(missing_ok=True)
    return False


def search_and_download(
    query: str,
    destination_dir: pathlib.Path,
    asset_id: str,
    exclude_titles: set[str] | None = None,
) -> dict | None:
    """Find the best free Commons image for a beat, download it, and return attribution."""
    clean_query = " ".join(str(query or "").split())[:180]
    if len(clean_query) < 3:
        return None

    search_queries = [clean_query]
    # Commons titles often use archival terminology; a narrower alternate improves recall.
    if len(clean_query.split()) >= 3:
        search_queries.append(" ".join(clean_query.split()[:4]))

    candidates: dict[str, dict] = {}
    for search_query in search_queries:
        try:
            response = api(
                action="query",
                generator="search",
                gsrsearch=search_query,
                gsrnamespace=6,
                gsrlimit=10,
                **IIPROP,
            )
        except Exception as exc:
            log.warning("Wikimedia Commons search failed for %r: %s", search_query, exc)
            continue
        pages = (response.get("query") or {}).get("pages", [])
        for page in sorted(pages, key=lambda value: value.get("index", 0)):
            metadata = info(page)
            if not FREE.search(metadata.get("license") or ""):
                continue
            if metadata.get("title") in (exclude_titles or set()):
                continue
            mime = str(metadata.get("mime") or "").lower()
            if mime not in {"image/jpeg", "image/png", "image/webp"}:
                continue
            score = _candidate_score(metadata, clean_query)
            if score > -1000:
                metadata["_score"] = score
                candidates[metadata["title"]] = metadata
        if candidates and max(item.get("_score", 0) for item in candidates.values()) >= 9.0:
            break

    if not candidates:
        return None

    selected = max(candidates.values(), key=lambda item: item["_score"])
    width = int(selected.get("w") or 0)
    url = (selected.get("thumb") if width > 1800 else None) or selected.get("url")
    if not url:
        return None
    suffix = pathlib.Path(urllib.parse.urlparse(url).path).suffix.lower()
    if suffix not in {".jpg", ".jpeg", ".png", ".webp"}:
        suffix = ".jpg"
    safe_id = re.sub(r"[^A-Za-z0-9_-]+", "_", asset_id)[:24]
    destination = pathlib.Path(destination_dir) / f"{safe_id}{suffix}"
    if not _download(url, destination):
        return None

    return {
        "id": asset_id,
        "path": str(destination),
        "filename": destination.name,
        "title": selected.get("title"),
        "credit": selected.get("credit") or "Creator not named on Commons",
        "license": selected.get("license"),
        "license_url": selected.get("license_url"),
        "source_url": selected.get("source"),
        "date": selected.get("date"),
        "description": selected.get("desc"),
        "query": clean_query,
        "width": width,
        "height": int(selected.get("h") or 0),
    }


def geocode_places(names: list[str]) -> dict[str, list[float]]:
    """Resolve explicitly named places using OpenStreetMap Nominatim, politely and conservatively."""
    import json

    resolved: dict[str, list[float]] = {}
    for name in dict.fromkeys(" ".join(str(value).split()) for value in names if str(value).strip()):
        params = urllib.parse.urlencode({"q": name, "format": "jsonv2", "limit": 1})
        request = urllib.request.Request(
            f"https://nominatim.openstreetmap.org/search?{params}",
            headers={"User-Agent": UA, "Accept": "application/json"},
        )
        try:
            with urllib.request.urlopen(request, timeout=20) as response:
                rows = json.loads(response.read().decode("utf-8"))
            if rows:
                resolved[name] = [float(rows[0]["lat"]), float(rows[0]["lon"])]
        except Exception as exc:
            log.info("place lookup failed for %r: %s", name, exc)
        time.sleep(1.1)  # respect the public Nominatim service's usage policy
    return resolved
