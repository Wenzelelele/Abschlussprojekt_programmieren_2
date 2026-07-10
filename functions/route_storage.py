"""
route_storage.py
-----------------
Speichert hochgeladene GPX-Routen pro Nutzer in einer TinyDB (JSON-Datei),
damit sie spaeter ueber eine Auswahlbox wieder geladen werden koennen,
ohne die Datei erneut hochladen zu muessen.

Jeder Eintrag enthaelt sowohl die schon berechneten Metadaten (Name,
Distanz, Aufstieg, Datum) fuer eine schnelle Anzeige in der Auswahlbox,
als auch den rohen GPX-Text, um die Route bei Bedarf neu einzulesen.
"""

import io
from datetime import datetime

from tinydb import Query, TinyDB

from data.gpx_processing import parse_gpx

DB_PATH = "data/routes_db.json"

# Ab dieser Anzahl gespeicherter Routen pro Nutzer wird beim naechsten Speichern
# die aelteste Route automatisch entfernt - vor allem damit die JSON-Datei nicht
# unbegrenzt waechst, da wir den vollen GPX-Text pro Route mit ablegen.
MAX_ROUTES_PER_USER = 10


def _get_table():
    db = TinyDB(DB_PATH)
    return db.table("routes")


def save_route(username: str, filename: str, gpx_text: str) -> None:
    """
    Parst eine GPX-Datei einmalig und speichert sie inkl. Metadaten fuer den Nutzer.

    Speichert nichts, wenn der Nutzer diese Datei (identischer GPX-Inhalt) schon
    hat - noetig, weil Streamlit bei jeder Interaktion (Slider, Auswahlbox, ...)
    das Skript neu ausfuehrt und der Uploader die Datei dabei jedes Mal erneut
    liefert, solange sie nicht entfernt wurde.
    """
    Route = Query()
    already_saved = _get_table().contains(
        (Route.username == username) & (Route.gpx_content == gpx_text)
    )
    if already_saved:
        return

    route = parse_gpx(io.StringIO(gpx_text))

    _get_table().insert({
        "username": username,
        "filename": filename,
        "route_name": route.name,
        "distance_km": round(route.total_distance_m / 1000.0, 2),
        "ascent_m": round(route.total_ascent_m),
        "uploaded_at": datetime.now().isoformat(timespec="seconds"),
        "gpx_content": gpx_text,
    })

    _prune_old_routes(username)


def _prune_old_routes(username: str) -> None:
    """Behaelt nur die MAX_ROUTES_PER_USER neuesten Routen eines Nutzers."""
    routes = get_routes_for_user(username)  # neueste zuerst

    excess_routes = routes[MAX_ROUTES_PER_USER:]
    if excess_routes:
        _get_table().remove(doc_ids=[r.doc_id for r in excess_routes])


def get_routes_for_user(username: str) -> list[dict]:
    """Liefert alle gespeicherten Routen eines Nutzers, neueste zuerst."""
    Route = Query()
    routes = _get_table().search(Route.username == username)
    return sorted(routes, key=lambda r: r["uploaded_at"], reverse=True)


def delete_route(doc_id: int) -> None:
    """Loescht eine einzelne gespeicherte Route anhand ihrer TinyDB doc_id."""
    _get_table().remove(doc_ids=[doc_id])
