"""
training_processing.py
-----------------------
Einlesen und Aufbereiten von historischen Trainingsdaten (GPX/FIT)
fuer den Trainingsdaten-Tab. Nutzt haversine_m aus gpx_processing.py
und grade_to_class aus pace_model.py, damit beide Tabs dieselbe
Distanzformel und dieselbe +-3%-Gelaende-Schwelle verwenden.
"""

import numpy as np
import pandas as pd

from data.gpx_processing import haversine_m
from functions.efficiency import calc_gap_pace
from functions.hr_zones import hr_to_zone
from functions.pace_model import grade_to_class

# Umrechnung FIT-Semicircles -> Grad (FIT speichert Koordinaten als
# 32-Bit-Ganzzahl ueber den vollen Kreis).
_SEMICIRCLES_TO_DEG = 180.0 / 2**31

# Unter dieser Distanz im Rolling Window gilt der Punkt als "Stehen"
# (Ampel, Pause) - Steigung/Pace waeren dort reines Rauschen.
MIN_WINDOW_DIST_M = 5.0

# Plausibilitaetsfenster fuer die Pace: schneller als 2:00 min/km ist
# GPS-Fehler, langsamer als 20:00 min/km ist Gehen/Pause - beides
# wuerde die EF-Mittelwerte verzerren.
MIN_PACE_SEC_PER_KM = 120.0
MAX_PACE_SEC_PER_KM = 1200.0


def _read_text(file_obj) -> str:
    """Liest ein Upload-Objekt (BytesIO/StringIO) robust als Text."""
    raw = file_obj.read()
    return raw.decode("utf-8") if isinstance(raw, bytes) else raw


def _extract_hr_from_extensions(point) -> float:
    """
    Sucht die Herzfrequenz in den GPX-Extensions eines Trackpunkts.
    Standard ist die Garmin TrackPointExtension mit einem <hr>-Element;
    wir vergleichen nur den lokalen Tag-Namen (ohne Namespace), damit
    auch Exporte anderer Anbieter (z.B. <heartrate>) funktionieren.
    """
    for ext in point.extensions:
        for element in ext.iter():
            tag = element.tag.rsplit("}", 1)[-1].lower()
            if tag in ("hr", "heartrate") and element.text:
                try:
                    return float(element.text)
                except ValueError:
                    continue
    return np.nan


def load_training_gpx(file_obj) -> pd.DataFrame:
    """
    Liest eine GPX-Datei eines vergangenen Trainingslaufs ein,
    inklusive Zeitstempel und Herzfrequenz (aus den GPX-Extensions).

    Input:  file_obj - hochgeladene GPX-Datei (z.B. aus st.file_uploader)
    Output: DataFrame mit Spalten: lat, lon, ele, time, hr
    """
    import gpxpy

    gpx = gpxpy.parse(_read_text(file_obj))

    rows = []
    for track in gpx.tracks:
        for segment in track.segments:
            for pt in segment.points:
                rows.append(
                    {
                        "lat": pt.latitude,
                        "lon": pt.longitude,
                        "ele": pt.elevation if pt.elevation is not None else np.nan,
                        "time": pt.time,
                        "hr": _extract_hr_from_extensions(pt),
                    }
                )

    if len(rows) < 2:
        raise ValueError("GPX-Datei enthaelt keine verwertbaren Trackpunkte.")

    df = pd.DataFrame(rows)
    if df["time"].isna().all():
        raise ValueError(
            "GPX-Datei enthaelt keine Zeitstempel - ohne <time> ist keine "
            "Pace-Berechnung moeglich (Strecken-GPX statt Trainings-GPX?)."
        )
    return _normalize_time(df)


def load_training_fit(file_obj) -> pd.DataFrame:
    """
    Liest eine FIT-Datei (z.B. Garmin-/Strava-Export) via garmin-fit-sdk
    ein. Die Rohdatei wird nach dem Parsen verworfen, nur das DataFrame
    bleibt bestehen.

    Input:  file_obj - hochgeladene FIT-Datei
    Output: DataFrame, gleiches Format wie load_training_gpx
    """
    from garmin_fit_sdk import Decoder, Stream

    raw = file_obj.read()
    stream = Stream.from_byte_array(bytearray(raw))
    messages, errors = Decoder(stream).read()
    if errors:
        raise ValueError(f"FIT-Datei konnte nicht gelesen werden: {errors}")

    rows = []
    for record in messages.get("record_mesgs", []):
        lat_sc = record.get("position_lat")
        lon_sc = record.get("position_long")
        if lat_sc is None or lon_sc is None:
            continue  # Punkte ohne GPS-Fix (z.B. Tunnel) ueberspringen
        rows.append(
            {
                "lat": lat_sc * _SEMICIRCLES_TO_DEG,
                "lon": lon_sc * _SEMICIRCLES_TO_DEG,
                "ele": record.get("enhanced_altitude", record.get("altitude", np.nan)),
                "time": record.get("timestamp"),
                "hr": record.get("heart_rate", np.nan),
            }
        )

    if len(rows) < 2:
        raise ValueError("FIT-Datei enthaelt keine verwertbaren GPS-Records.")

    return _normalize_time(pd.DataFrame(rows))


def _normalize_time(df: pd.DataFrame) -> pd.DataFrame:
    """
    Vereinheitlicht die Zeitstempel auf pandas-UTC. Noetig, weil gpxpy
    ein eigenes Timezone-Objekt (SimpleTZ) verwendet, das beim spaeteren
    pd.concat eines GPX-Runs mit einem FIT-Run (stdlib-UTC) kollidiert.
    """
    df["time"] = pd.to_datetime(df["time"], utc=True)
    return df


def preprocess(
    df: pd.DataFrame, zone_boundaries: dict, window: int = 60
) -> pd.DataFrame:
    """
    Glaettet Rohdaten (zeitbasiertes Rolling Window) und leitet die
    Kennzahlen fuer die Effizienz-Auswertung ab.

    Steigung und Pace werden bewusst NICHT von Punkt zu Punkt berechnet
    (GPS-Rauschen!), sondern ueber die Summen der letzten `window`
    Sekunden: grade = Hoehenmeter im Fenster / Distanz im Fenster.

    Input:  df - Rohdaten aus load_training_gpx/load_training_fit
            zone_boundaries - fertige HF-Zonen-Grenzen (von aussen
                aus hr_zones.py uebergeben, hier nicht berechnet)
            window - Fenstergroesse fuer die Glaettung (Sekunden)
    Output: df + Spalten: dist_delta_m, time_delta_s, ele_delta_m,
            grade_pct, pace_sec_per_km, gap_pace, hr_zone
    """
    out = (
        df.dropna(subset=["lat", "lon", "time"])
        .sort_values("time")
        .reset_index(drop=True)
        .copy()
    )
    if len(out) < 2:
        raise ValueError("Zu wenige gueltige Trackpunkte fuer die Auswertung.")

    # Luecken in Hoehe/HF interpolieren statt Zeilen zu verlieren
    out["ele"] = out["ele"].interpolate(limit_direction="both")
    out["hr"] = out["hr"].interpolate(limit_direction="both")

    # Deltas von Punkt zu Punkt (haversine_m ist skalar -> Schleife ueber
    # Punktepaare; bei typischen Laufdaten mit 1 Punkt/Sekunde unkritisch)
    lats, lons = out["lat"].to_numpy(), out["lon"].to_numpy()
    out["dist_delta_m"] = [0.0] + [
        haversine_m(lats[i - 1], lons[i - 1], lats[i], lons[i])
        for i in range(1, len(out))
    ]
    out["time_delta_s"] = out["time"].diff().dt.total_seconds().fillna(0.0)
    out["ele_delta_m"] = out["ele"].diff().fillna(0.0)

    # Zeitbasiertes Rolling Window: Summen der letzten `window` Sekunden
    rolled = (
        out.set_index("time")[["dist_delta_m", "time_delta_s", "ele_delta_m"]]
        .rolling(f"{window}s")
        .sum()
    )
    dist_w = rolled["dist_delta_m"].to_numpy()
    time_w = rolled["time_delta_s"].to_numpy()
    ele_w = rolled["ele_delta_m"].to_numpy()

    moving = dist_w > MIN_WINDOW_DIST_M
    with np.errstate(divide="ignore", invalid="ignore"):
        grade = np.where(moving, ele_w / dist_w * 100.0, np.nan)
        pace = np.where(moving & (time_w > 0), time_w / dist_w * 1000.0, np.nan)

    out["grade_pct"] = np.clip(grade, -40, 40)  # gleiche Grenze wie gpx_processing.py
    out["pace_sec_per_km"] = pace
    out["gap_pace"] = calc_gap_pace(out["pace_sec_per_km"], out["grade_pct"])
    out["hr_zone"] = out["hr"].map(lambda hr: hr_to_zone(hr, zone_boundaries))

    # Stillstand, Pausen und GPS-Ausreisser aus der Statistik entfernen
    plausible = out["pace_sec_per_km"].between(MIN_PACE_SEC_PER_KM, MAX_PACE_SEC_PER_KM)
    return out[plausible & out["hr"].notna()].reset_index(drop=True)


def calc_terrain_split(df: pd.DataFrame) -> pd.DataFrame:
    """
    Ordnet jedem Punkt eine Gelaendeart zu (nutzt grade_to_class aus
    pace_model.py, damit die +-3%-Schwelle im ganzen Projekt konsistent
    bleibt - keine eigene Klassifikationslogik).

    Input:  df - preprocessed DataFrame (mit grade_pct)
    Output: df + Spalte terrain ("up" / "flat" / "down")
    """
    out = df.copy()
    out["terrain"] = out["grade_pct"].map(grade_to_class)
    return out
