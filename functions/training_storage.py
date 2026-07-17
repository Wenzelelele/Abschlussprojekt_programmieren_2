"""
training_storage.py
--------------------
Speichert die fertigen Trainings-Aggregate pro Nutzer in einer TinyDB
(JSON-Datei), damit sie nach einem Login wieder verfuegbar sind, ohne
die Dateien neu hochladen zu muessen. Anders als bei route_storage.py
wird KEIN roher GPX/FIT-Inhalt abgelegt - nur die vier Kennzahlen,
und ein neuer Upload ersetzt die alten Werte komplett (upsert).
"""

from datetime import datetime

from tinydb import Query, TinyDB

DB_PATH = "data/training_db.json"


def _get_table():
    db = TinyDB(DB_PATH)
    return db.table("training_summaries")


def _to_plain_floats(nested: dict) -> dict:
    """
    Wandelt numpy-Floats in normale Python-Floats um (rekursiv fuer
    pace_hr_bins) - TinyDB speichert als JSON, und json.dump kennt
    numpy-Typen nicht.
    """
    return {
        key: _to_plain_floats(value) if isinstance(value, dict) else float(value)
        for key, value in nested.items()
    }


def save_training_summary(
    person_id: str,
    ef_factors: dict,
    pace_hr_bins: dict,
    max_distance_km: float,
    max_elevation_m: float,
    n_runs: int = 0,
) -> None:
    """
    Speichert (oder ueberschreibt) die Trainings-Aggregate einer Person.
    Ein Eintrag pro person_id (stabile user_id aus dem Profil) - upsert statt insert, damit ein neuer Upload
    die alten Werte ersetzt und kein Verlauf entsteht.
    """
    User = Query()
    _get_table().upsert(
        {
            "person_id": person_id,
            "ef_factors": _to_plain_floats(ef_factors),
            "pace_hr_bins": _to_plain_floats(pace_hr_bins),
            "max_distance_km": float(max_distance_km),
            "max_elevation_m": float(max_elevation_m),
            "n_runs": int(n_runs),
            "updated_at": datetime.now().isoformat(timespec="seconds"),
        },
        User.person_id == person_id,
    )


def load_training_summary(person_id: str) -> dict | None:
    """
    Laedt die gespeicherten Aggregate eines Nutzers (fuer den Login-Fall).
    Gibt None zurueck, falls noch nichts gespeichert wurde.
    """
    User = Query()
    return _get_table().get(User.person_id == person_id)
