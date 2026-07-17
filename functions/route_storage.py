"""
route_storage.py
-----------------
Speichert hochgeladene GPX-Routen pro Nutzer in einer TinyDB (JSON-Datei),
damit sie über eine Auswahlbox wieder geladen werden können, statt die
Datei erneut hochladen zu müssen. Jeder Eintrag hat sowohl die fertigen
Metadaten (Name, Distanz, Aufstieg, Datum) fuer die Auswahlbox als auch
den rohen GPX-Text zum Neu-Einlesen.
"""

import io
from datetime import datetime

from tinydb import Query, TinyDB

from data.gpx_processing import parse_gpx

DB_PATH = "data/routes_db.json"

# Ab dieser Anzahl gespeicherter Routen pro Nutzer wird beim nächsten Speichern
# die älteste Route automatisch entfernt - vor allem damit die JSON-Datei nicht
# unbegrenzt wächst, da wir den vollen GPX-Text pro Route mit ablegen.
MAX_ROUTES_PER_USER = 5


def _get_table():
    db = TinyDB(DB_PATH)
    return db.table("routes")


def save_route(username: str, filename: str, gpx_text: str) -> dict:
    """
    Parst eine GPX-Datei einmalig und speichert sie inkl. Metadaten für den Nutzer.

    Speichert nichts Neues, wenn dieselbe Datei (gleicher GPX-Inhalt) schon
    existiert - der Uploader liefert sie sonst bei jedem Rerun erneut.
    Gibt immer das Routen-Dokument zurück (neu oder vorhanden), damit der
    Aufrufer die Route direkt als aktive Auswahl setzen kann.
    """
    Route = Query()
    existing = _get_table().get(
        (Route.username == username) & (Route.gpx_content == gpx_text)
    )
    if existing is not None:
        return existing

    route = parse_gpx(io.StringIO(gpx_text))

    doc_id = _get_table().insert(
        {
            "username": username,
            "filename": filename,
            "route_name": route.name,
            "distance_km": round(route.total_distance_m / 1000.0, 2),
            "ascent_m": round(route.total_ascent_m),
            "uploaded_at": datetime.now().isoformat(timespec="seconds"),
            "gpx_content": gpx_text,
        }
    )

    _prune_old_routes(username)

    return _get_table().get(doc_id=doc_id)


def _prune_old_routes(username: str) -> None:
    """Behält nur die MAX_ROUTES_PER_USER neuesten Routen eines Nutzers."""
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
    """Löscht eine einzelne gespeicherte Route anhand ihrer TinyDB doc_id."""
    _get_table().remove(doc_ids=[doc_id])
