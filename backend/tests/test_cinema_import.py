"""OSM cleanup and offline import; all network responses are local fixtures."""
import importlib.util
import json
from pathlib import Path

import pytest

from tests.test_migrations import isolated_schema as isolated_schema

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("cinema_import", ROOT / "scripts/import_cinemas.py")
importer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(importer)


def element(key, name, latitude=18.5, longitude=73.8, **tags):
    return {"type": "node", "id": key, "lat": latitude, "lon": longitude,
            "tags": {"amenity": "cinema", "name": name, **tags}}


@pytest.mark.parametrize("name,brand,chain", [("INOX Leisure", "", "PVR INOX"), ("PVR", "", "PVR INOX"),
    ("Cinepolis West End", "", "Cinépolis"), ("Cinépolis", "", "Cinépolis"),
    ("Vishal E-Square", "", "E-Square"), ("E-Square Xion", "", "E-Square"),
    ("Abhiruchi City Pride", "", "City Pride"), ("Miraj cinemas", "", "Miraj"),
    ("Carnival Cinemas", "", "Carnival"), ("Cinema", "PVR", "PVR INOX"), ("Victory", "", "Independent")])
def test_chain_normalization(name, brand, chain):
    assert importer.chain_for(name, brand) == chain


def test_names_areas_dedup_and_overrides():
    places = [element(90, "Kothrud", 18.5, 73.8), element(91, "Hinjawadi", 18.6, 73.75)]
    data = [element(1, "PVR"), element(2, "INOX Leisure", latitude=18.5001, brand="INOX", **{"addr:suburb": "Kothrud"}),
            element(3, "Miraj cinemas", latitude=18.6, longitude=73.75),
            element(4, "E-Square Multiplex", latitude=18.65, **{"addr:city_district": "Wakad"})]
    clean = importer.clean_cinemas(data, places)
    assert len(clean) == 3
    assert next(c for c in clean if c["chain"] == "PVR INOX")["osm_id"] == "node/2"
    assert next(c for c in clean if c["chain"] == "PVR INOX")["name"] == "PVR INOX Kothrud"
    miraj = next(c for c in clean if c["chain"] == "Miraj")
    assert (miraj["name"], miraj["area"]) == ("Miraj Cinemas", "Hinjawadi")
    overrides = {"exclude": ["node/2"], "rename": {"node/3": "Miraj Test"}, "area": {"node/3": "Baner"}}
    changed = importer.apply_overrides(clean, overrides)
    assert len(changed) == 2 and next(c for c in changed if c["osm_id"] == "node/3")["area"] == "Baner"
    assert next(c for c in changed if c["osm_id"] == "node/3")["name"] == "Miraj Test"
    assert importer.distance((18.5, 73.8), (18.5001, 73.8)) < 300


def test_coordinate_centers_screen_tag_and_layout():
    way = {"type": "way", "id": 1, "center": {"lat": 18.5, "lon": 73.8},
           "tags": {"name": "PVR", "screen": "7", "addr:suburb": "Baner"}}
    assert importer.clean_cinemas([way], [])[0]["screens"] == 7
    assert importer.seat_layout("way/1", 2) == importer.seat_layout("way/1", 2)
    for number in range(1, 20):
        rows, columns, premium = importer.seat_layout("way/1", number)
        assert 8 <= rows <= 14 and 12 <= columns <= 20 and premium == 2
        rows, columns, premium = importer.seat_layout("way/1", number, False)
        assert 16 <= rows <= 20 and 22 <= columns <= 28 and premium == 4


def test_offline_import_keeps_layouts_and_deactivates_missing(isolated_schema):
    conn = isolated_schema
    conn.execute((ROOT / "db/schema.sql").read_text())
    cinemas = importer.load_snapshot()
    assert len(cinemas) >= 30
    assert importer.import_cinemas(conn, cinemas) > 0
    before = conn.execute("SELECT screen_id, count(*), max(row_label), max(seat_number) FROM seats GROUP BY screen_id ORDER BY screen_id").fetchall()
    assert importer.import_cinemas(conn, cinemas) == 0
    assert conn.execute("SELECT screen_id, count(*), max(row_label), max(seat_number) FROM seats GROUP BY screen_id ORDER BY screen_id").fetchall() == before
    assert conn.execute("SELECT DISTINCT format FROM screens ORDER BY format").fetchall() == [('2D',)]
    importer.import_cinemas(conn, cinemas[:-1])
    assert conn.execute("SELECT is_active FROM cinemas WHERE osm_id = %s", (cinemas[-1]["osm_id"],)).fetchone() == (False,)
    assert conn.execute("SELECT count(*) FROM cinemas").fetchone()[0] == len(cinemas) + 1


def test_offline_override_file(tmp_path):
    overrides = tmp_path / "overrides.json"
    snapshot = importer.load_snapshot()
    overrides.write_text(json.dumps({"exclude": [snapshot[0]["osm_id"]]}))
    assert len(importer.load_snapshot(overrides_path=overrides)) == len(snapshot) - 1


def test_overpass_retries_mirrors_and_joins_geometry(monkeypatch):
    import io
    import urllib.error
    calls = []
    def urlopen(request, timeout):
        calls.append(request.full_url)
        assert request.get_header("User-agent") == "CineBook-importer"
        if len(calls) == 1:
            raise urllib.error.HTTPError(request.full_url, 429, "busy", {}, None)
        if len(calls) == 2:
            raise ConnectionResetError()
        return io.BytesIO(json.dumps({"elements": [
            {"type": "node", "id": 1, "tags": {"name": "Cinema"}},
            {"type": "node", "id": 1, "lat": 18.5, "lon": 73.8}]}).encode())
    monkeypatch.setattr(importer.urllib.request, "urlopen", urlopen)
    monkeypatch.setattr(importer.time, "sleep", lambda seconds: None)
    result = importer.fetch("query", attempts=2)
    assert calls == [importer.MIRRORS[0], importer.MIRRORS[0], importer.MIRRORS[1]]
    assert result[0]["tags"]["name"] == "Cinema" and result[0]["lat"] == 18.5
