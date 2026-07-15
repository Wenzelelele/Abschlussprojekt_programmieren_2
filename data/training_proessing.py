"""
training_processing.py
-----------------------
Einlesen und Aufbereiten von historischen Trainingsdaten (GPX/FIT)
für den Trainingsdaten-Tab. Nutzt haversine_m aus gpx_processing.py,
damit beide Tabs dieselbe Distanzformel verwenden.
"""

import pandas as pd

from data.gpx_processing import haversine_m
from functions.pace_model import grade_to_class


def load_training_gpx(file_obj) -> pd.DataFrame:
    """
    Liest eine GPX-Datei eines vergangenen Trainingslaufs ein,
    inklusive Zeitstempel und Herzfrequenz (aus den GPX-Extensions).

    Input:  file_obj - hochgeladene GPX-Datei (z.B. aus st.file_uploader)
    Output: DataFrame mit Spalten: lat, lon, ele, time, hr
    """
    raise NotImplementedError("TODO: gpxpy nutzen, Extension-Felder für HR auslesen")


def load_training_fit(file_obj) -> pd.DataFrame:
    """
    Liest eine FIT-Datei (z.B. Strava-Export) ein. Die Rohdatei wird
    nach dem Parsen verworfen, nur das DataFrame bleibt bestehen.

    Input:  file_obj - hochgeladene FIT-Datei
    Output: DataFrame, gleiches Format wie load_training_gpx
    """
    raise NotImplementedError("TODO: fitparse nutzen, records iterieren")


def preprocess(df: pd.DataFrame, window: int = 60) -> pd.DataFrame:
    """
    Glättet Rohdaten (Rolling Window) und leitet Kennzahlen ab.

    Input:  df - Rohdaten aus load_training_gpx/load_training_fit
            window - Fenstergröße für die Glättung (Sekunden)
    Output: df + neue Spalten: grade_pct, pace_sec_per_km, gap_pace, hr_zone
    """
    raise NotImplementedError(
        "TODO: rolling() auf Distanz/Zeit/HF, dann grade/pace ableiten"
    )


def calc_terrain_split(df: pd.DataFrame) -> pd.DataFrame:
    """
    Ordnet jedem Punkt eine Geländeart zu (nutzt grade_to_class aus
    pace_model.py, damit die ±3%-Schwelle konsistent bleibt).

    Input:  df - preprocessed DataFrame (mit grade_pct)
    Output: df + Spalte terrain ("up" / "flat" / "down")
    """
    raise NotImplementedError("TODO: grade_to_class vektorisiert anwenden")
