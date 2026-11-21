"""Editable geometry, curated venue rules, protected relayout and recliner checkout."""
import json
import shutil
from email import policy
from email.parser import BytesParser
from pathlib import Path

import psycopg
import pytest
from psycopg.rows import dict_row

from app import email
from app.seat_layouts import LAYOUT_ROOT, build_seats, load_layout, select_layout, validate_layout
from tests.test_cinema_import import importer
from tests.test_local_contract import show as show
from tests.test_migrations import isolated_schema as isolated_schema

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize("name,rows,width,count", [("multiplex-small",10,16,124), ("multiplex-medium",12,24,206),
    ("multiplex-large",15,28,312), ("lounge",4,14,40), ("single-screen",20,32,554)])
def test_templates_valid_aligned_staggered_and_accessible(name,rows,width,count):
    layout = load_layout(LAYOUT_ROOT / f"{name}.json")
    patterns = [value.split()[1] for value in layout["rows"]]
    assert len(patterns) == rows and {len(p) for p in patterns} == {width}
    seats = build_seats(layout)
    assert len(seats) == count
    if name.startswith("multiplex"):
        assert sum(seat["accessible"] for seat in seats) == 2
        assert all(s["row_index"] == 0 and s["seat_type"] == "REGULAR" for s in seats if s["accessible"])
        assert sum(c != '.' for c in patterns[0]) < max(sum(c != '.' for c in p) for p in patterns)
        aisles = {"multiplex-small":[7],"multiplex-medium":[4,19],"multiplex-large":[7,20]}[name]
        assert all(p[col] == '.' for p in patterns for col in aisles)
    if name == "multiplex-large":
        assert patterns[6] == '.' * width
    if name == "single-screen":
        assert patterns[13] == '.' * width
    if name == "lounge":
        assert {s["seat_type"] for s in seats} == {"RECLINER"}


@pytest.mark.parametrize("rows,error", [([],"1 to 30"), (["A R"]*31,"1 to 30"),
    (["A R","A R"],"row A: duplicate"), (["a R"],"row a: label"), (["A RX"],"row A: pattern"),
    (["A RR","B R"],"row B: width"), (["A "+"R"*41],"row A: at most 40"), (["A ..."],"at least one seat"),
    (["A"],"row 1: expected")])
def test_bad_layout_names_file_and_row(rows,error):
    with pytest.raises(ValueError,match=error) as caught:
        validate_layout({"name":"Broken","rows":rows},"broken-audi.json")
    assert "broken-audi.json" in str(caught.value) and "row" in str(caught.value)


def test_gap_numbering_and_override_priority(tmp_path):
    layout = validate_layout({"name":"Tiny","rows":["A R.WL","B P.PP"]})
    seats = build_seats(layout)
    assert [(s["seat_number"],s["col"]) for s in seats if s["row_label"] == "A"] == [(1,1),(2,3),(3,4)]
    assert seats[1]["accessible"] and seats[2]["seat_type"] == "RECLINER"
    folder = tmp_path / "screens/pune-test"
    folder.mkdir(parents=True)
    (folder / "Audi 1.json").write_text(json.dumps(layout))
    name, selected = select_layout("pune-test","Audi 1","nonexistent-template",root=tmp_path)
    assert name == "screens/pune-test/Audi 1" and selected["name"] == "Tiny"
    with pytest.raises(ValueError,match="plain path"):
        select_layout("../outside","Audi 1","lounge",root=tmp_path)


def test_curated_upsert_defaults_lounges_no_invented_formats_and_cleanup(isolated_schema):
    conn = isolated_schema
    conn.execute((ROOT / "db/schema.sql").read_text())
    cinemas = importer.load_curated()
    result = importer.import_curated(conn,cinemas)
    assert result["screens_created"] == 84
    assert conn.execute("SELECT count(*) FROM cinemas WHERE is_active").fetchone() == (20,)
    assert conn.execute("SELECT DISTINCT format FROM screens").fetchall() == [('2D',)]
    for key in ("pune-pvr-director-s-cut-kopa-mall","pune-moviemax-gold-mariplex-mall"):
        assert conn.execute("SELECT count(*) FROM screens sc JOIN cinemas c ON c.id=sc.cinema_id WHERE c.source_key=%s AND sc.layout_name='lounge'", (key,)).fetchone() == (4,)
    assert conn.execute("SELECT count(*) FROM screens sc JOIN cinemas c ON c.id=sc.cinema_id WHERE c.name LIKE %s AND sc.name='VIP' AND sc.layout_name='lounge'", ('%Seasons Mall%',)).fetchone() == (1,)
    ids_before = conn.execute("SELECT id FROM seats ORDER BY id").fetchall()
    changed = [{**c, "area":"Updated area"} if index == 0 else c for index,c in enumerate(cinemas)]
    assert importer.import_curated(conn,changed)["screens_created"] == 0
    assert conn.execute("SELECT area FROM cinemas WHERE source_key = %s", (cinemas[0]["key"],)).fetchone() == ('Updated area',)
    assert conn.execute("SELECT id FROM seats ORDER BY id").fetchall() == ids_before
    # A superseded venue loses only future shows with no booking or live hold.
    first = conn.execute("SELECT sc.id FROM screens sc JOIN cinemas c ON c.id=sc.cinema_id WHERE c.source_key=%s ORDER BY sc.id LIMIT 1", (cinemas[0]["key"],)).fetchone()[0]
    movie = conn.execute("INSERT INTO movies (title,language,certificate,duration_minutes) VALUES ('Test','Hindi','U',120) RETURNING id").fetchone()[0]
    shows = [conn.execute("INSERT INTO shows (screen_id,movie_id,start_time,regular_price,premium_price) VALUES (%s,%s,now()+(%s * interval '1 day'),200,300) RETURNING id", (first,movie,offset)).fetchone()[0] for offset in (1,2,3)]
    customer = conn.execute("INSERT INTO customers (full_name,email) VALUES ('Test','keep@example.com') RETURNING id").fetchone()[0]
    conn.execute("INSERT INTO bookings (booking_ref,customer_id,show_id,total_amount) VALUES ('KEEP',%s,%s,200)", (customer,shows[0]))
    seat = conn.execute("SELECT id FROM seats WHERE screen_id=%s LIMIT 1", (first,)).fetchone()[0]
    conn.execute("INSERT INTO seat_holds (hold_id,show_id,seat_ids,expires_at) VALUES ('keep',%s,%s,now()+interval '5 minutes')", (shows[1],[seat]))
    importer.import_curated(conn,cinemas[1:])
    assert conn.execute("SELECT id FROM shows WHERE id = ANY(%s) ORDER BY id", (shows,)).fetchall() == [(shows[0],),(shows[1],)]
    assert conn.execute("SELECT is_active FROM cinemas WHERE source_key=%s", (cinemas[0]["key"],)).fetchone() == (False,)


def test_relayout_skips_bookings_and_live_holds_uses_override(isolated_schema,tmp_path):
    conn = isolated_schema
    conn.execute((ROOT / "db/schema.sql").read_text())
    cinemas = importer.load_curated()[:1]
    importer.import_curated(conn,cinemas,schedule=False)
    screens = [r[0] for r in conn.execute("SELECT id FROM screens ORDER BY id")]
    before = {screen:conn.execute("SELECT id FROM seats WHERE screen_id=%s ORDER BY id", (screen,)).fetchall() for screen in screens}
    movie = conn.execute("INSERT INTO movies (title,language,certificate,duration_minutes) VALUES ('Test','Hindi','U',120) RETURNING id").fetchone()[0]
    shows = [conn.execute("INSERT INTO shows (screen_id,movie_id,start_time,regular_price,premium_price) VALUES (%s,%s,now()+interval '1 day',200,300) RETURNING id", (screen,movie)).fetchone()[0] for screen in screens]
    customer = conn.execute("INSERT INTO customers (full_name,email) VALUES ('Booked','booked@example.com') RETURNING id").fetchone()[0]
    conn.execute("INSERT INTO bookings (booking_ref,customer_id,show_id,total_amount,status) VALUES ('OLD',%s,%s,200,'CANCELLED')", (customer,shows[0]))
    conn.execute("INSERT INTO seat_holds (hold_id,show_id,seat_ids,expires_at) VALUES ('live',%s,%s,now()+interval '5 minutes')", (shows[1],[before[screens[1]][0][0]]))
    for path in LAYOUT_ROOT.glob('*.json'):
        shutil.copy2(path,tmp_path/path.name)
    folder = tmp_path/'screens'/cinemas[0]['key']
    folder.mkdir(parents=True)
    (folder/'Audi 3.json').write_text(json.dumps({'name':'Custom','rows':['A RW.WR','B LL.LL'],'section_names':{'R':'Standard','L':'Lounge'}}))
    result = importer.import_curated(conn,cinemas,relayout=True,layout_root=tmp_path,schedule=False)
    assert result['screens_skipped'] == 2 and result['screens_relaid'] == 2
    for screen in screens[:2]:
        assert conn.execute("SELECT id FROM seats WHERE screen_id=%s ORDER BY id", (screen,)).fetchall() == before[screen]
    assert conn.execute("SELECT count(*) FROM seats WHERE screen_id=%s", (screens[2],)).fetchone() == (8,)
    assert conn.execute("SELECT layout_name FROM screens WHERE id=%s", (screens[2],)).fetchone()[0].endswith('/Audi 3')


def test_recliner_local_flow_geometry_sections_prices_email_sms(client,show,database_url,monkeypatch,tmp_path):
    monkeypatch.setattr(email,'OUTBOX',tmp_path)
    seatmap = client.get(f"/shows/{show['id']}/seats").json()
    assert seatmap['layout_name'] == 'multiplex-large' and seatmap['grid'] == {'rows':15,'cols':28}
    assert [s['seat_type'] for s in seatmap['sections']] == ['RECLINER','PREMIUM','REGULAR']
    assert seatmap['sections'][0]['row_labels'] == ['N','O']
    assert all(s['row_index'] == 0 and s['col'] in (7,22) for s in seatmap['seats'] if s['accessible'])
    recliner = next(s for s in seatmap['seats'] if s['seat_type'] == 'RECLINER')
    assert recliner['price'] == '630.00'  # fixture premium=350, fallback recliner=630
    assert seatmap['sections'][0]['price'] == '630.00'
    held = client.post(f"/shows/{show['id']}/holds",json={'seat_ids':[recliner['id']]}).json()
    assert held['seats'][0]['seat_type'] == 'RECLINER' and held['total_amount'] == '630.00'
    assert client.get('/holds/'+held['hold_id']).json()['total_amount'] == '630.00'
    response = client.post('/bookings',json={'hold_id':held['hold_id'],'full_name':'Recliner Tester','email':show['email'],
                                           'phone':'9800000001','sms_consent':True})
    assert response.status_code == 202,response.text
    booking = client.get('/bookings/'+response.json()['booking_ref']).json()
    assert booking['status'] == 'CONFIRMED' and booking['total_amount'] == '630.00'
    assert booking['seats'][0]['seat_type'] == 'RECLINER' and booking['seats'][0]['price'] == '630.00'
    content = BytesParser(policy=policy.default).parsebytes(next(tmp_path.glob('*.eml')).read_bytes()).get_content()
    assert 'Recliner' in content and '630.00' in content and 'DEMO TICKET' in content
    with psycopg.connect(database_url,row_factory=dict_row) as conn:
        sms = conn.execute("SELECT body FROM sms_messages WHERE booking_id=(SELECT id FROM bookings WHERE booking_ref=%s)", (booking['booking_ref'],)).fetchone()['body']
    assert 'Recliner' in sms and 'DEMO' in sms and len(sms) <= 160


def test_legacy_geometry_stays_null(client,database_url):
    with psycopg.connect(database_url,autocommit=True) as conn:
        screen = conn.execute("SELECT sc.id FROM screens sc JOIN cinemas ci ON ci.id=sc.cinema_id WHERE ci.source_key IS NULL AND sc.layout_name IS NULL ORDER BY sc.id LIMIT 1").fetchone()[0]
        movie = conn.execute("SELECT id FROM movies WHERE is_active LIMIT 1").fetchone()[0]
        show_id = conn.execute("INSERT INTO shows (screen_id,movie_id,start_time,regular_price,premium_price) VALUES (%s,%s,now()+interval '10 days',200,300) RETURNING id", (screen,movie)).fetchone()[0]
        try:
            data = client.get(f'/shows/{show_id}/seats').json()
            assert data['grid'] is None and data['layout_name'] is None
            assert all(s['col'] is None and s['row_index'] is None and not s['accessible'] for s in data['seats'])
        finally:
            conn.execute("DELETE FROM shows WHERE id=%s", (show_id,))
