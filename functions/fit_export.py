"""
fit_export.py
--------------
Export der geplanten Strecke als FIT-Workout-Datei, mit dem offiziellen
Garmin FIT Python SDK (garmin-fit-sdk, uv add garmin-fit-sdk).

GRUNDIDEE:
Im Gegensatz zum einfachen GPX-Export (der nur eine "Strecke" mit
Text-Hinweisen ist) ist eine FIT-Workout-Datei ein STRUKTURIERTES
Workout: Garmin-Geräte können pro Abschnitt aktiv anzeigen/warnen,
ob man im Ziel-Pace-Bereich läuft.

WICHTIGE TECHNISCHE DETAILS:

1. Das FIT-Format kennt keine "Pace" direkt, sondern nur "Speed" (m/s).
   Ein Pace-Ziel wird deshalb als Geschwindigkeits-BEREICH gespeichert
   (custom_target_value_low/high), nicht als exakter Punktwert - so
   arbeiten Garmin-Workouts grundsätzlich.

2. Die Sub-Felder von FIT (z.B. "custom_target_speed_low" mit Skalierung
   1000, oder "duration_distance" mit Skalierung 100) werden vom
   garmin-fit-sdk NUR BEIM LESEN (Decoder) automatisch aufgelöst, NICHT
   beim Schreiben (Encoder). Der Encoder verwendet beim Schreiben immer
   die Skalierung des GENERISCHEN Feldnamens (z.B. "custom_target_value_low"),
   die 1 beträgt (keine Skalierung). Deshalb müssen wir die Werte SELBST
   vorskalieren (z.B. speed_m_s * 1000) und unter dem generischen
   Feldnamen abspeichern - nicht unter dem spezifischen Sub-Feld-Namen,
   den der Encoder gar nicht kennt.
   Das wurde mit einem Schreib-Lese-Rundlauf-Test gegen das SDK verifiziert.

3. Bei Nutzung von Custom-Zielwerten (Bereich statt fixer Zone) MUSS
   das normale "target_value"-Feld auf 0 gesetzt werden - sonst wissen
   Garmin-Geräte nicht, ob sie den einzelnen Wert oder den Bereich
   verwenden sollen (Hinweis aus dem offiziellen Garmin-Entwicklerforum).

GRUPPIERUNG:
Damit nicht 100+ winzige 100m-Schritte entstehen, werden aufeinander-
folgende Segmente mit gleicher Steigungsklasse (up/flat/down) zu EINEM
Workout-Schritt zusammengefasst (siehe group_segments_by_grade_class).
"""


from datetime import datetime, timezone

import pandas as pd

from functions.pace_model import grade_to_class


# Breite des Pace-Zielbereichs: +/- diese Anzahl Sekunden pro km um die
# berechnete Ziel-Pace herum.
PACE_TARGET_TOLERANCE_SEC = 15.0


# ---------------------------------------------------------------------
# Schritt 1: Segmente zu Bloecken gleicher Steigungsklasse zusammenfassen
# ---------------------------------------------------------------------

def group_segments_by_grade_class(segments: pd.DataFrame) -> pd.DataFrame:
    """
    Fasst aufeinanderfolgende Segmente mit derselben Steigungsklasse
    (up/flat/down) zu einem Block zusammen.

    Eingabe: segments mit "start_m", "end_m", "grade_pct", "pace_sec_per_km"
    (Ergebnis von estimate_segments_for_zone oder estimate_zone_for_target_time).

    Rückgabe: ein DataFrame mit einer Zeile pro Block:
        start_m, end_m, distance_m, grade_class, avg_pace_sec_per_km
    """
    working = segments.copy()
    working["grade_class"] = working["grade_pct"].apply(grade_to_class)

    # Blockgrenzen erkennen: immer wenn sich die Klasse gegenüber dem
    # vorherigen Segment ändert, beginnt ein neuer Block.
    class_changed = working["grade_class"] != working["grade_class"].shift(1)
    block_id = class_changed.cumsum()

    blocks = []
    for _, block_df in working.groupby(block_id):
        # Pace-Mittelwert des Blocks gewichtet nach Segmentlänge, damit
        # längere Segmente innerhalb des Blocks stärker zählen.
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
    Segment) und gibt die rohen Bytes zurück (zum Speichern oder als
    Streamlit-Download).

    Jeder Schritt im Workout entspricht einem Block gleicher Steigungs-
    klasse (siehe group_segments_by_grade_class), mit:
    - Dauer: Distanz des Blocks in Metern
    - Ziel: Geschwindigkeits-Bereich (aus der Ziel-Pace +/- Toleranz)
    """
    from garmin_fit_sdk import Encoder, Profile

    blocks = group_segments_by_grade_class(segments)

    encoder = Encoder()

    # --- FILE_ID: sagt Garmin, dass dies eine Workout-Datei ist ---
    encoder.write_mesg({
        "mesg_num": Profile["mesg_num"]["FILE_ID"],
        "type": "workout",
        "manufacturer": "development",
        "product": 0,
        "time_created": datetime.now(tz=timezone.utc),
        "serial_number": 1,
    })

    # --- WORKOUT: Name, Sportart, Anzahl Schritte ---
    encoder.write_mesg({
        "mesg_num": Profile["mesg_num"]["WORKOUT"],
        "wkt_name": workout_name[:15],  # FIT begrenzt Namen typischerweise auf kurze Strings
        "sport": "running",
        "num_valid_steps": len(blocks),
    })

    # --- WORKOUT_STEP: ein Schritt pro Block ---
    for i, block in blocks.iterrows():
        pace = block["avg_pace_sec_per_km"]

        # Ziel-Pace +/- Toleranz -> in Speed umrechnen. WICHTIG: eine
        # LANGSAMERE Pace (mehr sec/km) entspricht einer NIEDRIGEREN
        # Geschwindigkeit - die obere Pace-Grenze wird zur UNTEREN
        # Speed-Grenze und umgekehrt.
        pace_slow_bound = pace + pace_tolerance_sec  # langsamer = höhere sec/km
        pace_fast_bound = max(pace - pace_tolerance_sec, 60.0)  # Sicherheitsnetz: min 1:00/km

        speed_low_ms = pace_sec_per_km_to_speed_ms(pace_slow_bound)
        speed_high_ms = pace_sec_per_km_to_speed_ms(pace_fast_bound)

        grade_label = GRADE_CLASS_LABELS_DE.get(block["grade_class"], "")
        step_name = f"{grade_label} {block['distance_m']/1000:.1f}km"[:15]

        encoder.write_mesg({
            "mesg_num": Profile["mesg_num"]["WORKOUT_STEP"],
            "message_index": int(i),
            "wkt_step_name": step_name,
            "duration_type": "distance",
            # Sub-Feld "duration_distance" hat Skalierung 100 -> selbst
            # vorskalieren, der Encoder wendet diese Skalierung nicht
            # automatisch an (siehe Modul-Docstring, Punkt 2).
            "duration_value": round(block["distance_m"] * 100),
            "target_type": "speed",
            "target_value": 0,  # 0 = Custom-Bereich statt fester Zone nutzen
            # Sub-Felder "custom_target_speed_low/high" haben Skalierung
            # 1000 -> ebenfalls selbst vorskaliert.
            "custom_target_value_low": round(speed_low_ms * 1000),
            "custom_target_value_high": round(speed_high_ms * 1000),
            "intensity": "active",
        })

    return encoder.close()