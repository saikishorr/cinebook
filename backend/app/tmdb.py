"""TMDB transport and film metadata shared by the importer and authenticated admin."""
import json
import time
import urllib.error
import urllib.parse
import urllib.request

API = "https://api.themoviedb.org/3"
IMAGES = "https://image.tmdb.org/t/p"
TIMEOUT = 15
ATTEMPTS = 10

# ISO 639-1 code -> the language name shown on the website.
LANGUAGES = {
    "mr": "Marathi", "hi": "Hindi", "en": "English", "te": "Telugu", "ta": "Tamil",
    "ml": "Malayalam", "kn": "Kannada", "bn": "Bengali", "pa": "Punjabi", "gu": "Gujarati",
    "ja": "Japanese", "ko": "Korean", "es": "Spanish", "fr": "French", "zh": "Chinese", "cn": "Cantonese",
    "de": "German", "it": "Italian", "th": "Thai", "or": "Odia", "as": "Assamese", "bho": "Bhojpuri",
}

DEFAULT_RUNTIME = 140


class Tmdb:
    def __init__(self, key: str):
        self.key = key.strip()
        # The v4 read token is a JWT (starts with "eyJ"); the v3 key is 32 hex characters.
        self.bearer = self.key.startswith("eyJ")

    def get(self, path: str, **params) -> dict:
        if not self.bearer:
            params["api_key"] = self.key
        url = f"{API}{path}?{urllib.parse.urlencode(params)}"
        headers = {"Accept": "application/json", "User-Agent": "CineBook-importer"}
        if self.bearer:
            headers["Authorization"] = f"Bearer {self.key}"
        # Some Indian ISPs reset a share of connections to api.themoviedb.org (partial blocking),
        # so dropped connections are retried generously; each retry is a fresh connection.
        for attempt in range(ATTEMPTS):
            last = attempt == ATTEMPTS - 1
            try:
                with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=TIMEOUT) as response:
                    return json.loads(response.read().decode("utf-8"))
            except urllib.error.HTTPError as error:
                if error.code == 401:
                    raise SystemExit("TMDB rejected the key (401). Check TMDB_API_KEY in backend/.env.") from None
                if error.code in (429, 500, 502, 503, 504) and not last:   # rate limited or busy: wait and retry
                    time.sleep(min(2 * (attempt + 1), 8))
                    continue
                # Never print the URL: with a v3 key it contains the key.
                raise SystemExit(f"TMDB request {path} failed with HTTP {error.code}") from None
            except (urllib.error.URLError, TimeoutError, ConnectionError) as error:
                if not last:
                    time.sleep(0.5 + 0.25 * attempt)
                    continue
                reason = getattr(error, "reason", error)
                raise SystemExit(
                    f"Could not reach TMDB after {ATTEMPTS} tries ({reason.__class__.__name__}). Your internet provider "
                    "may be blocking api.themoviedb.org: try a VPN, Cloudflare WARP, or another network such as a "
                    "mobile hotspot.") from None
        raise SystemExit(f"TMDB request {path} kept failing")


def certificate(release_dates: dict, adult: bool) -> str:
    """Map TMDB's Indian certification to the U / UA / A values the database allows.
    CBFC's newer UA 7+ / UA 13+ / UA 16+ all count as UA; S (specialised audiences) counts as A."""
    for country in release_dates.get("results", []):
        if country.get("iso_3166_1") != "IN":
            continue
        for item in country.get("release_dates", []):
            value = (item.get("certification") or "").upper().replace(" ", "").replace("/", "")
            if not value:
                continue
            if value.startswith("UA"):
                return "UA"
            if value in ("U", "A"):
                return value
            if value == "S":
                return "A"
    return "A" if adult else "UA"


def trailer(videos: dict) -> str | None:
    clips = [v for v in videos.get("results", []) if v.get("site") == "YouTube" and v.get("type") == "Trailer"]
    clips.sort(key=lambda v: (not v.get("official"), v.get("published_at") or ""))
    return f"https://www.youtube.com/watch?v={clips[0]['key']}" if clips else None


def details(tmdb: Tmdb, movie: dict) -> dict:
    full = tmdb.get(f"/movie/{movie['id']}", language="en-IN", append_to_response="release_dates,videos")
    code = full.get("original_language") or movie.get("original_language")
    return {
        "tmdb_id": full["id"],
        "title": full.get("title") or movie.get("title"),
        "description": (full.get("overview") or "").strip() or None,
        "duration_minutes": full.get("runtime") or DEFAULT_RUNTIME,
        "language": LANGUAGES.get(code, code.upper() if code else "Unknown"),
        "certificate": certificate(full.get("release_dates", {}), bool(full.get("adult"))),
        "poster_url": f"{IMAGES}/w500{full['poster_path']}" if full.get("poster_path") else None,
        "backdrop_url": f"{IMAGES}/w1280{full['backdrop_path']}" if full.get("backdrop_path") else None,
        "trailer_url": trailer(full.get("videos", {})),
        "genres": [g["name"] for g in full.get("genres", [])],
        "release_date": full.get("release_date") or None,
    }


