"""Best-effort TMDB integration that fills the existing Movie / MovieCast /
MovieMedia records. It never raises to callers for API problems (except
``TmdbError`` from the bulk-discovery helpers, which the import command handles).

Rules this module follows:
* Existing data always wins. A movie that already has cast members or a
  trailer keeps them; TMDB only fills what is missing. That makes every
  operation safe to re-run and avoids duplicates.
* A TMDB match for an existing movie is only accepted when title *and*
  release year agree.
* All database writes for one movie happen in a single transaction, so a
  failed import never leaves a half-created movie behind.
"""
from __future__ import annotations

import json
import logging
import re
import time
from dataclasses import dataclass
from datetime import date
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from django.conf import settings
from django.core.files.base import ContentFile
from django.db import transaction

from critix.models import Movie, MovieCast, MovieMedia

logger = logging.getLogger(__name__)

TMDB_API_ROOT = "https://api.themoviedb.org/3"
TMDB_IMAGE_BASE = "https://image.tmdb.org/t/p"
POSTER_SIZE = "w500"
PROFILE_SIZE = "w185"  # cast photos are shown at ~112px, so w185 keeps disk use small
MAX_CAST = 20
MAX_DISCOVER_PAGES = 500  # TMDB will not return pages beyond 500
# Trailer preference order; other video types (clips, featurettes) are ignored.
TRAILER_PREFERENCE = ("Trailer", "Teaser")


class TmdbError(Exception):
    """Raised by bulk-discovery helpers when TMDB cannot be queried."""


@dataclass
class SyncResult:
    matched: bool = False
    cast_added: int = 0
    trailer_added: bool = False
    reason: str = ""

    def __bool__(self):  # keeps `if sync_movie_metadata(movie):` working
        return self.matched


@dataclass
class ImportResult:
    status: str  # created | linked | skipped | failed
    movie: Movie | None = None
    cast_added: int = 0
    trailer_added: bool = False
    reason: str = ""


# --------------------------------------------------------------------------
# HTTP helpers
# --------------------------------------------------------------------------
def _credentials():
    api_key = (getattr(settings, "TMDB_API_KEY", "") or "").strip()
    access_token = (getattr(settings, "TMDB_ACCESS_TOKEN", "") or "").strip()
    # A v4 "Read Access Token" (a long JWT starting with "eyJ") is a common thing to
    # paste into the API-key variable by mistake; treat it as the token it is.
    if api_key.startswith("eyJ") and not access_token:
        api_key, access_token = "", api_key
    return api_key, access_token


def _request_json(path: str, **params):
    """Single TMDB request; raises on any failure."""
    api_key, access_token = _credentials()
    if not access_token:
        params.setdefault("api_key", api_key)
    params.setdefault("language", getattr(settings, "TMDB_LANGUAGE", "en-US"))
    headers = {"Accept": "application/json", "User-Agent": "Critix/1.0"}
    if access_token:
        headers["Authorization"] = f"Bearer {access_token}"
    root = (getattr(settings, "TMDB_API_ROOT", "") or TMDB_API_ROOT).rstrip("/")
    request = Request(f"{root}{path}?{urlencode(params)}", headers=headers)
    with urlopen(request, timeout=10) as response:
        return json.loads(response.read().decode("utf-8"))


def _get_json(path: str, **params):
    api_key, access_token = _credentials()
    if not api_key and not access_token:
        return None
    attempts = 3
    for attempt in range(1, attempts + 1):
        try:
            return _request_json(path, **params)
        except HTTPError as exc:  # 401/404 etc. will not improve by retrying
            logger.warning("TMDB request failed for %s: HTTP %s", path, exc.code)
            return None
        except Exception as exc:  # resets/timeouts are often transient; metadata must never break movie creation
            if attempt == attempts:
                logger.warning("TMDB request failed for %s: %s", path, exc)
                return None
            time.sleep(attempt)


def check_connection() -> tuple[bool, str]:
    """Cheap pre-flight: are credentials set, accepted, and is TMDB reachable?"""
    api_key, access_token = _credentials()
    if not api_key and not access_token:
        return False, "No TMDB_API_KEY / TMDB_ACCESS_TOKEN is set in this terminal."
    attempts = 3
    for attempt in range(1, attempts + 1):
        try:
            _request_json("/configuration")
            return True, "OK"
        except HTTPError as exc:
            if exc.code in (401, 403):
                return False, (
                    f"TMDB rejected the credentials (HTTP {exc.code}). Use the 32-character API Key (v3) in "
                    "TMDB_API_KEY, or the long Read Access Token in TMDB_ACCESS_TOKEN. Check for typos or "
                    "leftover placeholder text."
                )
            return False, f"TMDB answered with HTTP {exc.code}."
        except Exception as exc:  # connection resets are often transient, so retry before giving up
            if attempt < attempts:
                time.sleep(attempt)
                continue
            return False, (
                f"Could not reach TMDB after {attempts} tries ({exc}). Your network/ISP/antivirus is probably "
                "blocking or resetting the connection to api.themoviedb.org. Try switching DNS to 1.1.1.1 or "
                "8.8.8.8, a VPN, another network such as a phone hotspot, or set "
                "TMDB_API_ROOT=https://api.tmdb.org/3 to use TMDB's alternate API hostname."
            )


def _download_image(path: str | None, size: str) -> bytes | None:
    if not path:
        return None
    attempts = 3
    for attempt in range(1, attempts + 1):
        try:
            request = Request(f"{TMDB_IMAGE_BASE}/{size}{path}", headers={"User-Agent": "Critix/1.0"})
            with urlopen(request, timeout=10) as response:
                return response.read()
        except HTTPError as exc:
            logger.warning("Could not download TMDB image %s: HTTP %s", path, exc.code)
            return None
        except Exception as exc:
            if attempt == attempts:
                logger.warning("Could not download TMDB image %s: %s", path, exc)
                return None
            time.sleep(attempt)


# --------------------------------------------------------------------------
# Matching a local Movie to a TMDB movie (pure functions, no DB access)
# --------------------------------------------------------------------------
def _normalize(text: str | None) -> str:
    return re.sub(r"[\W_]+", " ", (text or "").casefold()).strip()


def _result_year(item: dict) -> int | None:
    date_str = (item.get("release_date") or "")[:4]
    return int(date_str) if date_str.isdigit() else None


def _is_partial_title(a: str, b: str) -> bool:
    """True when the shorter title (2+ words) appears whole inside the longer one."""
    short, long_ = sorted((a, b), key=len)
    return len(short.split()) >= 2 and f" {short} " in f" {long_} "


def _score_result(title: str, year: int | None, item: dict, preferred_language: str = ""):
    """Return a sortable score for a TMDB hit, or None if it is not a
    trustworthy match for the local movie."""
    wanted = _normalize(title)
    names = {n for n in (_normalize(item.get("title")), _normalize(item.get("original_title"))) if n}
    if not wanted or not names:
        return None

    result_year = _result_year(item)
    gap = abs(result_year - year) if (result_year and year) else None
    if gap is not None and gap > 1:
        return None  # same name, different film

    if wanted in names:
        match = 2
    else:
        # Local titles are often shortened ("Aravinda Sametha" for
        # "Aravinda Sametha Veera Raghava"). Accept containment only for
        # multi-word titles and only when the release year is an exact match.
        if gap != 0 or not any(_is_partial_title(wanted, n) for n in names):
            return None
        match = 1

    language_ok = int(bool(preferred_language) and item.get("original_language") == preferred_language)
    exact_year = int(gap == 0)
    return (match, language_ok, exact_year, item.get("popularity") or 0)


def _pick_match(title: str, year: int | None, results: list[dict], preferred_language: str = "") -> int | None:
    scored = []
    for item in results:
        score = _score_result(title, year, item, preferred_language)
        if score is not None and item.get("id"):
            scored.append((score, item["id"]))
    return max(scored)[1] if scored else None


def _find_tmdb_id(movie: Movie) -> int | None:
    if movie.tmdb_id:
        return movie.tmdb_id
    preferred = getattr(settings, "TMDB_PREFERRED_ORIGINAL_LANGUAGE", "")
    # First ask TMDB to filter by year, then retry without it in case our
    # release_year is off by one; _pick_match still enforces year +/- 1.
    for extra in ({"year": movie.release_year}, {}):
        data = _get_json("/search/movie", query=movie.title, **extra)
        found = _pick_match(movie.title, movie.release_year, (data or {}).get("results") or [], preferred)
        if found:
            return found
    return None


# --------------------------------------------------------------------------
# Trailer selection and genre formatting (pure)
# --------------------------------------------------------------------------
def _pick_trailer(videos: dict | None) -> dict | None:
    candidates = [
        v for v in ((videos or {}).get("results") or [])
        if v.get("site") == "YouTube" and v.get("key") and v.get("type") in TRAILER_PREFERENCE
    ]
    if not candidates:
        return None
    # Official Trailer > any Trailer > official Teaser > any Teaser.
    return min(
        candidates,
        key=lambda v: (TRAILER_PREFERENCE.index(v["type"]), not v.get("official", False)),
    )


def _video_languages() -> str:
    lang = getattr(settings, "TMDB_LANGUAGE", "en-US")[:2]
    preferred = getattr(settings, "TMDB_PREFERRED_ORIGINAL_LANGUAGE", "")
    return ",".join(dict.fromkeys(filter(None, [preferred, lang, "en", "null"])))


def _genre_string(details: dict) -> str:
    """Format genres the way the existing site stores them: 'Action/Comedy' (max 100 chars)."""
    names = [g["name"].strip() for g in (details.get("genres") or []) if g.get("name")]
    return "/".join(names[:3])[:100] or "Unknown"


def _is_latin_title(title: str) -> bool:
    return all(ord(ch) < 0x250 or not ch.isalpha() for ch in title)


# --------------------------------------------------------------------------
# Shared cast / trailer writing
# --------------------------------------------------------------------------
def _fetch_details(tmdb_id: int) -> dict | None:
    return _get_json(
        f"/movie/{tmdb_id}",
        append_to_response="credits,videos",
        include_video_language=_video_languages(),
    )


def _prepare_cast(details: dict, max_cast: int) -> list[dict]:
    """Build cast rows (downloading photos). Network work only; no database access."""
    payload, seen = [], set()
    for position, item in enumerate(((details.get("credits") or {}).get("cast") or [])[:max_cast]):
        name = (item.get("name") or "").strip()
        if not name or name.casefold() in seen:
            continue
        seen.add(name.casefold())
        payload.append({
            "name": name[:150],
            "role": (item.get("character") or "").strip()[:150],
            "sort_order": item.get("order", position),
            "photo": _download_image(item.get("profile_path"), PROFILE_SIZE),
        })
    return payload


def _write_cast_and_trailer(movie: Movie, cast_payload: list[dict], trailer: dict | None, result) -> None:
    """Call inside transaction.atomic(). Only fills what is missing."""
    # Re-check inside the transaction so concurrent runs cannot double-insert.
    if cast_payload and not movie.cast_members.exists():
        for row in cast_payload:
            member = MovieCast(movie=movie, name=row["name"], role=row["role"], sort_order=row["sort_order"])
            if row["photo"]:  # otherwise the template's existing initial-letter fallback shows
                member.photo.save(f"tmdb_{movie.pk}_{row['sort_order']}.jpg", ContentFile(row["photo"]), save=False)
            member.save()
            result.cast_added += 1

    if trailer and not movie.media_assets.filter(media_type="trailer").exists():
        MovieMedia.objects.create(
            movie=movie,
            media_type="trailer",
            url=f"https://www.youtube.com/watch?v={trailer['key']}",
            caption=(trailer.get("name") or "Official trailer")[:200],
            sort_order=0,
        )
        result.trailer_added = True


# --------------------------------------------------------------------------
# Enrich an existing movie
# --------------------------------------------------------------------------
def sync_movie_metadata(movie: Movie, tmdb_id: int | None = None, max_cast: int = MAX_CAST) -> SyncResult:
    """Fill missing cast and trailer for ``movie`` from TMDB.

    Existing cast members / trailers are never modified or duplicated.
    Pass ``tmdb_id`` to pin a specific TMDB movie when title matching fails.
    """
    api_key, access_token = _credentials()
    if not api_key and not access_token:
        logger.info("TMDB credentials are not configured; skipping enrichment for %s", movie)
        return SyncResult(reason="TMDB_API_KEY / TMDB_ACCESS_TOKEN not set")

    need_cast = not movie.cast_members.exists()
    need_trailer = not movie.media_assets.filter(media_type="trailer").exists()
    if not need_cast and not need_trailer:
        return SyncResult(reason="already has cast and trailer")

    tmdb_id = tmdb_id or _find_tmdb_id(movie)
    if not tmdb_id:
        return SyncResult(reason="no confident TMDB match (title + year)")
    if Movie.objects.filter(tmdb_id=tmdb_id).exclude(pk=movie.pk).exists():
        return SyncResult(reason=f"TMDB id {tmdb_id} already belongs to another movie")

    details = _fetch_details(tmdb_id)
    if not details:
        return SyncResult(reason="TMDB request failed")

    # Network work (image downloads) happens before the transaction so the
    # database is not locked while waiting on the CDN.
    cast_payload = _prepare_cast(details, max_cast) if need_cast else []
    trailer = _pick_trailer(details.get("videos")) if need_trailer else None

    result = SyncResult(matched=True)
    with transaction.atomic():
        if movie.tmdb_id != tmdb_id:
            movie.tmdb_id = tmdb_id
            movie.save(update_fields=["tmdb_id"])
        _write_cast_and_trailer(movie, cast_payload, trailer, result)
    return result


# --------------------------------------------------------------------------
# Bulk import (Telugu catalogue via TMDB "discover")
# --------------------------------------------------------------------------
# --------------------------------------------------------------------------
# Where to watch (TMDB watch-provider data, sourced from JustWatch)
# --------------------------------------------------------------------------
def _logo_url(logo_path: str | None) -> str:
    return f"{TMDB_IMAGE_BASE}/w92{logo_path}" if logo_path else ""


def fetch_watch_providers(tmdb_id: int, region: str | None = None) -> dict:
    """Return {"flatrate": [...], "rent": [...], "buy": [...]} of {"name", "logo"} for one region."""
    region = (region or getattr(settings, "TMDB_WATCH_REGION", "IN") or "IN").upper()
    data = _get_json(f"/movie/{tmdb_id}/watch/providers")
    by_region = ((data or {}).get("results") or {}).get(region) or {}
    providers = {}
    for kind in ("flatrate", "rent", "buy"):
        providers[kind] = [
            {"name": p.get("provider_name", ""), "logo": _logo_url(p.get("logo_path"))}
            for p in by_region.get(kind, [])
        ]
    return providers


def sync_watch_providers(movie: Movie, tmdb_id: int | None = None, region: str | None = None, force: bool = False) -> bool:
    """Fill ``movie.watch_providers`` from TMDB. Independent of cast/trailer sync so it can be
    re-run on its own (providers change often). Returns True if the movie was updated."""
    if movie.watch_providers and not force:
        return False
    tmdb_id = tmdb_id or movie.tmdb_id or _find_tmdb_id(movie)
    if not tmdb_id:
        return False
    providers = fetch_watch_providers(tmdb_id, region=region)
    if not any(providers.values()):
        return False
    movie.watch_providers = providers
    if not movie.tmdb_id:
        movie.tmdb_id = tmdb_id
    movie.save(update_fields=["watch_providers", "tmdb_id"])
    return True


# --------------------------------------------------------------------------
# Coming soon (upcoming Telugu releases)
# --------------------------------------------------------------------------
def fetch_upcoming_releases(original_language: str = "te", region: str | None = None, max_results: int = 12) -> list[dict]:
    """Telugu-language titles with a future release date, newest-announced first."""
    region = (region or getattr(settings, "TMDB_WATCH_REGION", "IN") or "IN").upper()
    today = date.today().isoformat()
    data = _get_json(
        "/discover/movie",
        with_original_language=original_language,
        region=region,
        **{"primary_release_date.gte": today},
        sort_by="primary_release_date.asc",
    ) or {}
    rows = []
    for item in (data.get("results") or [])[:max_results]:
        release_date = item.get("release_date")
        if not release_date:
            continue
        rows.append({
            "tmdb_id": item.get("id"),
            "title": (item.get("title") or "").strip()[:200],
            "poster_url": f"{TMDB_IMAGE_BASE}/{POSTER_SIZE}{item['poster_path']}" if item.get("poster_path") else "",
            "release_date": release_date,
            "overview": item.get("overview", ""),
        })
    return rows


def fetch_trailer_url(tmdb_id: int) -> str:
    details = _get_json(f"/movie/{tmdb_id}", append_to_response="videos", include_video_language=_video_languages())
    trailer = _pick_trailer((details or {}).get("videos"))
    return f"https://www.youtube.com/watch?v={trailer['key']}" if trailer else ""

def _parse_date(value):
    """TMDB sends release dates as 'YYYY-MM-DD'; return a date or None."""
    try:
        return date.fromisoformat(value) if value else None
    except ValueError:
        return None
def _discover(year: int, page: int, min_votes: int, original_language: str):
    return _get_json(
        "/discover/movie",
        **{
            "with_original_language": original_language,
            "primary_release_year": year,
            "primary_release_date.lte": date.today().isoformat(),  # skip unreleased films
            "vote_count.gte": min_votes,
            "sort_by": "popularity.desc",
            "include_adult": "false",
            "page": page,
        },
    )


def discover_count(year: int, min_votes: int = 5, original_language: str = "te") -> int:
    data = _discover(year, 1, min_votes, original_language)
    if data is None:
        raise TmdbError(f"TMDB discover failed for {year}")
    return int(data.get("total_results") or 0)


def iter_discover(from_year: int, to_year: int, min_votes: int = 5, original_language: str = "te"):
    """Yield ``(year, item)`` for every matching TMDB film, one release year at a time.

    Raises ``TmdbError`` if a page cannot be fetched, so the caller can stop
    cleanly and resume later.
    """
    for year in range(from_year, to_year + 1):
        page = 1
        while True:
            data = _discover(year, page, min_votes, original_language)
            if data is None:
                raise TmdbError(f"TMDB discover failed for {year} (page {page})")
            for item in data.get("results") or []:
                yield year, item
            if page >= min(int(data.get("total_pages") or 1), MAX_DISCOVER_PAGES):
                break
            page += 1


def import_movie(
    tmdb_id: int,
    *,
    max_cast: int = 10,
    require_poster: bool = True,
    latin_titles_only: bool = False,
    local_candidates: list | None = None,
) -> ImportResult:
    """Create one Movie (poster, cast, trailer) from a TMDB id, atomically.

    ``local_candidates`` are existing movies without a tmdb_id. If one of them is
    the same film (title + year), it is linked and only its missing cast/trailer
    are filled, so importing never duplicates a movie you already have.
    """
    if Movie.objects.filter(tmdb_id=tmdb_id).exists():
        return ImportResult("skipped", reason="already imported")

    details = _fetch_details(tmdb_id)
    if not details:
        return ImportResult("failed", reason="TMDB request failed")

    title = (details.get("title") or "").strip()
    year = _result_year(details)
    if not title or not year:
        return ImportResult("skipped", reason="missing title or release date")
    if latin_titles_only and not _is_latin_title(title):
        return ImportResult("skipped", reason="non-Latin title")

    trailer = _pick_trailer(details.get("videos"))

    # Is this a movie we already have (without a tmdb_id)? Link instead of duplicating.
    local = next(
        (m for m in (local_candidates or []) if _score_result(m.title, m.release_year, details) is not None),
        None,
    )
    if local is not None:
        need_cast = not local.cast_members.exists()
        need_trailer = not local.media_assets.filter(media_type="trailer").exists()
        cast_payload = _prepare_cast(details, max_cast) if need_cast else []
        outcome = ImportResult("linked", movie=local)
        with transaction.atomic():
            local.tmdb_id = tmdb_id
            local.save(update_fields=["tmdb_id"])
            _write_cast_and_trailer(local, cast_payload, trailer if need_trailer else None, outcome)
        local_candidates.remove(local)
        return outcome

    poster = _download_image(details.get("poster_path"), POSTER_SIZE)
    if require_poster and poster is None:
        reason = "no poster on TMDB" if not details.get("poster_path") else "poster download failed"
        return ImportResult("skipped" if not details.get("poster_path") else "failed", reason=reason)

    cast_payload = _prepare_cast(details, max_cast)

    outcome = ImportResult("created")
    with transaction.atomic():
        movie = Movie(
            title=title[:200],
            genre=_genre_string(details),
            description=(details.get("overview") or "").strip(),
            release_year=year,
            release_date=_parse_date(details.get("release_date")),
            tmdb_id=tmdb_id,
        )
        if poster:
            movie.poster.save(f"tmdb_{tmdb_id}.jpg", ContentFile(poster), save=False)
        movie.save()
        outcome.movie = movie
        _write_cast_and_trailer(movie, cast_payload, trailer, outcome)
    return outcome