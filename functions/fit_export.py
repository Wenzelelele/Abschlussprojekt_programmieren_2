"""
fit_export.py
--------------
Export der geplanten Strecke als FIT-Workout-Datei (garmin-fit-sdk).

Wichtig zu wissen:
- FIT kennt keine "Pace", nur "Speed" (m/s) - Ziel-Pace wird deshalb als
  Geschwindigkeits-Bereich (low/high) gespeichert.
- Die Sub-Feld-Skalierungen (z.B. *1000 fuer Speed, *100 fuer Distanz)
  wendet der Encoder beim Schreiben NICHT automatisch an (nur der Decoder
  beim Lesen) - deshalb skalieren wir hier selbst und speichern unter dem
  generischen Feldnamen.
- target_value muss bei Custom-Bereichen auf 0 stehen, sonst wissen
  Garmin-Geräte nicht, ob sie den Einzelwert oder den Bereich nutzen sollen.
"""

from datetime import datetime, timezone

import pandas as pd

from functions.pace_model import grade_to_class


# Breite des Pace-Zielbereichs: +/- diese Anzahl Sekunden pro km um die
# berechnete Ziel-Pace herum.
PACE_TARGET_TOLERANCE_SEC = 15.0


# ---------------------------------------------------------------------
# Schritt 1: Segmente zu Blöcken gleicher Steigungsklasse zusammenfassen
# ---------------------------------------------------------------------

def group_segments_by_grade_class(segments: pd.DataFrame) -> pd.DataFrame:
    """
    Fasst aufeinanderfolgende Segmente mit derselben Steigungsklasse
    (up/flat/down) zu einem Block zusammen.

    Rückgabe: ein DataFrame mit einer Zeile pro Block:
        start_m, end_m, distance_m, grade_class, avg_pace_sec_per_km
    """
    working = segments.copy()
    working["grade_class"] = working["grade_pct"].apply(grade_to_class)

    # neuer Block, sobald sich die Klasse gegenueber davor aendert
    class_changed = working["grade_class"] != working["grade_class"].shift(1)
    block_id = class_changed.cumsum()

    blocks = []
    for _, block_df in working.groupby(block_id):
        # Pace-Mittelwert gewichtet nach Segmentlaenge
        seg_lengths = block_df["end_m"] - block_df["start_m"]
        total_length = seg_lengths.sum()
        if total_length > 0:
            weighted_pace = (block_df["pace_sec_per_km"] * seg_lengths).sum() / total_length
        else:
            weighted_pace = block_df["pace_sec_per_km"].mean()

        blocks.append({
            "start_m": block_df["start_m"].iloc[0],
            "end_m": block_df["end_m"].iloc[-1],
            "distance_m": total_length,
            "grade_class": block_df["grade_class"].iloc[0],
            "avg_pace_sec_per_km": weighted_pace,
        })

    return pd.DataFrame(blocks)


# ---------------------------------------------------------------------
# Schritt 2: Pace (sec/km) <-> Speed (m/s) Umrechnung
# ---------------------------------------------------------------------

def pace_sec_per_km_to_speed_ms(pace_sec_per_km: float) -> float:
    """Wandelt eine Pace (sec/km) in eine Geschwindigkeit (m/s) um."""
    if pace_sec_per_km <= 0:
        return 0.0
    return 1000.0 / pace_sec_per_km


GRADE_CLASS_LABELS_DE = {
    "up": "Bergauf",
    "flat": "Flach",
    "down": "Bergab",
}


# ---------------------------------------------------------------------
# Schritt 3: FIT-Workout-Datei bauen
# ---------------------------------------------------------------------

def build_fit_workout(
    segments: pd.DataFrame,
    workout_name: str = "Streckenplanung",
    pace_tolerance_sec: float = PACE_TARGET_TOLERANCE_SEC,
) -> bytes:
    """
    Baut eine FIT-Workout-Datei aus den Streckensegmenten (mit Pace pro
    Segment). Jeder Schritt entspricht einem Block gleicher Steigungsklasse
    (siehe group_segments_by_grade_class), mit Dauer = Blockdistanz und
    Ziel = Geschwindigkeits-Bereich aus Ziel-Pace +/- Toleranz.
    """
    from garmin_fit_sdk import Encoder, Profile

    blocks = group_segments_by_grade_class(segments)

    encoder = Encoder()

    # FILE_ID: sagt Garmin, dass dies eine Workout-Datei ist
    encoder.write_mesg({
        "mesg_num": Profile["mesg_num"]["FILE_ID"],
        "type": "workout",
        "manufacturer": "development",
        "product": 0,
        "time_created": datetime.now(tz=timezone.utc),
        "serial_number": 1,
    })

    # WORKOUT: Name, Sportart, Anzahl Schritte
    encoder.write_mesg({
        "mesg_num": Profile["mesg_num"]["WORKOUT"],
        "wkt_name": workout_name[:15],  # FIT begrenzt Namen typischerweise auf kurze Strings
        "sport": "running",
        "num_valid_steps": len(blocks),
    })

    # WORKOUT_STEP: ein Schritt pro Block
    for i, block in blocks.iterrows():
        pace = block["avg_pace_sec_per_km"]

        # langsamere Pace = niedrigere Speed -> obere Pace-Grenze wird
        # zur unteren Speed-Grenze und umgekehrt
        pace_slow_bound = pace + pace_tolerance_sec
        pace_fast_bound = max(pace - pace_tolerance_sec, 60.0)  # min 1:00/km

        speed_low_ms = pace_sec_per_km_to_speed_ms(pace_slow_bound)
        speed_high_ms = pace_sec_per_km_to_speed_ms(pace_fast_bound)

        grade_label = GRADE_CLASS_LABELS_DE.get(block["grade_class"], "")
        step_name = f"{grade_label} {block['distance_m']/1000:.1f}km"[:15]

        encoder.write_mesg({
            "mesg_num": Profile["mesg_num"]["WORKOUT_STEP"],
            "message_index": int(i),
            "wkt_step_name": step_name,
            "duration_type": "distance",
            "duration_value": round(block["distance_m"] * 100),  # Skalierung 100, selbst vorskaliert
            "target_type": "speed",
            "target_value": 0,  # 0 = Custom-Bereich statt fester Zone
            "custom_target_value_low": round(speed_low_ms * 1000),  # Skalierung 1000
            "custom_target_value_high": round(speed_high_ms * 1000),
            "intensity": "active",
        })

    return encoder.close()
