"""
training_processing.py
-----------------------
Einlesen und Aufbereiten von historischen Trainingsdaten (GPX/FIT)
fuer den Trainingsdaten-Tab. Nutzt haversine_m aus gpx_processing.py
und grade_to_class aus pace_model.py, damit beide Tabs dieselbe
Distanzformel und dieselbe +-3%-Gelaende-Schwelle verwenden.
"""

import xml.etree.ElementTree as ET

import numpy as np
import pandas as pd

from data.gpx_processing import haversine_m
from functions.efficiency import calc_gap_pace
from functions.hr_zones import hr_to_zone
from functions.pace_model import grade_to_class

# Einheitliche, kurze Nutzer-Meldungen fuer nicht verwertbare Dateien
NOT_A_RUN_MSG = "Das ist kein Lauf - bitte lade eine Lauf-Aktivität hoch."
INVALID_FILE_MSG = (
    "Diese Datei ist nicht gültig (z.B. fehlende Herzfrequenz) - "
    "bitte versuch eine andere Aktivität."
)

# Best-Effort-Erkennung von Nicht-Lauf-GPX ueber das optionale <trk><type>-Tag.
# GPX hat kein verpflichtendes Sport-Feld - fehlt das Tag, lassen wir die
# Datei durch (keine Info ist nicht dasselbe wie falsche Info).
_NON_RUN_TYPE_HINTS = (
    "bike",
    "biking",
    "cycling",
    "ride",
    "radfahr",
    "rad",
    "ski",
    "swim",
    "schwimm",
    "hike",
    "wander",
    "walk",
)

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

    # Sportart-Check (best effort): nur wenn das optionale type-Tag klar
    # auf eine andere Sportart hinweist, lehnen wir ab.
    for track in gpx.tracks:
        track_type = (track.type or "").lower()
        if any(hint in track_type for hint in _NON_RUN_TYPE_HINTS):
            raise ValueError(NOT_A_RUN_MSG)

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
        raise ValueError(INVALID_FILE_MSG)

    df = pd.DataFrame(rows)
    if df["time"].isna().all():
        raise ValueError(INVALID_FILE_MSG)
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
        raise ValueError(INVALID_FILE_MSG)

    # Sportart-Check: FIT kennt die Sportart explizit (session.sport).
    # Allow-Liste statt Aufzaehlung aller Nicht-Lauf-Sportarten: nur
    # "running" wird akzeptiert; fehlt die Angabe, lassen wir durch.
    sessions = messages.get("session_mesgs") or []
    sport = sessions[0].get("sport") if sessions else None
    if sport is not None and sport != "running":
        raise ValueError(NOT_A_RUN_MSG)

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
        raise ValueError(INVALID_FILE_MSG)

    return _normalize_time(pd.DataFrame(rows))


def load_training_tcx(file_obj) -> pd.DataFrame:
    """
    Liest eine TCX-Datei ein (Garmin Training Center XML, z.B. direkter
    Export aus Garmin Connect oder Wahoo). TCX ist reines XML mit festem
    Schema - wir nutzen die Standardbibliothek, keine neue Abhaengigkeit.

    Sportart-Check: TCX kennt am <Activity>-Tag nur "Running", "Biking"
    und "Other". "Biking" wird abgelehnt; "Other" ist ein Catch-all und
    wird durchgelassen (keine Info ist nicht dasselbe wie falsche Info).

    Input:  file_obj - hochgeladene TCX-Datei
    Output: DataFrame, gleiches Format wie load_training_gpx
    """
    try:
        root = ET.fromstring(_read_text(file_obj))
    except ET.ParseError:
        raise ValueError(INVALID_FILE_MSG)

    def _local(tag: str) -> str:
        """Tag-Name ohne XML-Namespace ('{ns}Trackpoint' -> 'Trackpoint')."""
        return tag.rsplit("}", 1)[-1]

    rows = []
    for activity in root.iter():
        if _local(activity.tag) != "Activity":
            continue
        if activity.get("Sport") == "Biking":
            raise ValueError(NOT_A_RUN_MSG)

        for tp in activity.iter():
            if _local(tp.tag) != "Trackpoint":
                continue
            point = {
                "lat": np.nan,
                "lon": np.nan,
                "ele": np.nan,
                "time": None,
                "hr": np.nan,
            }
            for el in tp.iter():
                tag, text = _local(el.tag), (el.text or "").strip()
                if tag == "HeartRateBpm":
                    # <HeartRateBpm><Value>142</Value></HeartRateBpm>
                    for child in el:
                        if _local(child.tag) == "Value" and child.text:
                            point["hr"] = float(child.text)
                elif not text:
                    continue
                elif tag == "Time":
                    point["time"] = text
                elif tag == "LatitudeDegrees":
                    point["lat"] = float(text)
                elif tag == "LongitudeDegrees":
                    point["lon"] = float(text)
                elif tag == "AltitudeMeters":
                    point["ele"] = float(text)
            if point["time"] is not None:
                rows.append(point)

    if len(rows) < 2:
        raise ValueError(INVALID_FILE_MSG)

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
    df: pd.DataFrame, zone_boundaries: dict, window: int = 30
) -> pd.DataFrame:
    """
    Glaettet Rohdaten (zeitbasiertes Rolling Window) und leitet die
    Kennzahlen fuer die Effizienz-Auswertung ab.

    Steigung und Pace werden bewusst NICHT von Punkt zu Punkt berechnet
    (GPS-Rauschen!), sondern ueber die Summen der letzten `window`
    Sekunden: grade = Hoehenmeter im Fenster / Distanz im Fenster.

    WARUM 30s (nicht mehr 60s): Wenzels Routen-Segmentierung in
    gpx_processing.py (resample_route) rechnet mit festen 100m-Segmenten.
    Bei typischem Renntempo (~3 m/s) entsprechen 100m ca. 30-35s - ein
    60s-Fenster deckt dagegen ~180-200m ab und glaettet damit deutlich
    staerker als Wenzels Segmente. Die Diskrepanz faellt vor allem bei
    der Rueckrechnung von GAP- auf reale Pace auf (calc_real_pace_from_gap
    nutzt die exakte, kaum geglaettete Segment-Steigung), weil die
    Minetti-Formel bei stark unterschiedlichen Steigungswerten stark
    unterschiedliche Umrechnungsfaktoren liefert - eine bei 60s geglaettete
    Steigung von z.B. 10% kann an derselben Stelle bei 100m-Segmenten als
    25% erscheinen, was die vorhergesagte Pace dort massiv verzerrt.
    30s ist ein Kompromiss: bei zuegigem Tempo nah an 100m, bei langsamem
    Bergauf-Gehen bleibt eine Restluecke (kein perfektes Matching ueber
    ein einfaches Zeitfenster moeglich, da Wenzels Segmente distanz- und
    unsere zeitbasiert bleiben - vollstaendige Angleichung waere eine
    groessere Umstellung).

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
        raise ValueError(INVALID_FILE_MSG)

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
    result = out[plausible & out["hr"].notna()].reset_index(drop=True)

    if result.empty:
        raise ValueError(INVALID_FILE_MSG)
    return result


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
