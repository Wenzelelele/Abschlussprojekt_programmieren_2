"""
pace_model.py
-------------
Schritt 1: Effizienz-Korrektur aus den 3 Efficiency-Factor-Werten
(bergauf / flach / bergab).

GRUNDIDEE:
Der Efficiency Factor (EF) ist eine Standard-Lauf-Metrik:
    EF = Geschwindigkeit (m/min) / durchschnittliche Herzfrequenz (bpm)
Ein höherer EF bedeutet: schneller bei gleicher Herzfrequenz = effizienter.

Wir bekommen 3 EF-Werte (einen pro Geländeart: bergauf, flach, bergab).
Diese vergleichen wir UNTEREINANDER (nicht gegen einen externen Sollwert),
um zu sehen, in welcher Geländeart die Person relativ zu sich selbst
stärker oder schwächer ist.

Beispiel zum Verstehen:
    ef_up   = 0.95
    ef_flat = 1.10
    ef_down = 1.20
    Durchschnitt = (0.95 + 1.10 + 1.20) / 3 = 1.0833

    factor_up   = 0.95   / 1.0833 = 0.877   -> deutlich unter 1 -> bergauf eher schwach
    factor_flat = 1.10   / 1.0833 = 1.015   -> knapp über 1 -> leicht überdurchschnittlich
    factor_down = 1.20   / 1.0833 = 1.108   -> klar über 1 -> bergab stark

Diese Faktoren multiplizieren wir später auf die Basis-Pace aus den Bins.
Wichtig: ein Faktor > 1 bedeutet "stark" und muss die Pace SCHNELLER machen
(also die Sekunden pro Kilometer verkleinern) - deshalb teilen wir die Pace
durch den Faktor, statt zu multiplizieren (siehe Schritt 2).
"""


def compute_ef_factors(ef_up: float, ef_flat: float, ef_down: float) -> dict:
    """
    Berechnet für jede Geländeart einen relativen Stärke-Faktor,
    indem der jeweilige EF durch den Durchschnitt aller drei EF-Werte
    geteilt wird.

    Rückgabe: {"up": factor, "flat": factor, "down": factor}
    Ein Faktor von 1.0 bedeutet "durchschnittlich stark in dieser Geländeart
    im Vergleich zu den eigenen anderen Geländearten".
    Ein Faktor > 1.0 bedeutet "überdurchschnittlich stark".
    Ein Faktor < 1.0 bedeutet "unterdurchschnittlich stark".
    """
    avg_ef = (ef_up + ef_flat + ef_down) / 3.0

    if avg_ef <= 0:
        # Sicherheitsnetz: ungültige Eingabe (EF sollte nie 0 oder negativ sein)
        return {"up": 1.0, "flat": 1.0, "down": 1.0}

    return {
        "up": ef_up / avg_ef,
        "flat": ef_flat / avg_ef,
        "down": ef_down / avg_ef,
    }


def apply_ef_factor(base_pace_sec_per_km: float, ef_factor: float) -> float:
    """
    Wendet einen EF-Stärke-Faktor auf eine Basis-Pace an.

    WICHTIG zum Verstehen: Pace ist in Sekunden pro Kilometer - eine
    KLEINERE Zahl bedeutet SCHNELLER. Ein Stärke-Faktor > 1 (überdurch-
    schnittlich stark) soll die Pace schneller machen, also die Sekunden-
    Zahl verkleinern. Deshalb wird hier DURCH den Faktor geteilt, nicht
    multipliziert:

        neue_pace = basis_pace / ef_factor

    Beispiel: basis_pace = 300 sec/km (5:00/km), ef_factor = 1.1 (10%
    stärker als der eigene Durchschnitt)
        -> neue_pace = 300 / 1.1 = 272.7 sec/km (4:33/km, schneller)

    Beispiel: ef_factor = 0.9 (10% schwächer)
        -> neue_pace = 300 / 0.9 = 333.3 sec/km (5:33/km, langsamer)
    """
    if ef_factor <= 0:
        return base_pace_sec_per_km
    return base_pace_sec_per_km / ef_factor


# ---------------------------------------------------------------------
# Schritt 3: Steigungsklasse bestimmen + Pace-Lookup mit EF-Korrektur
# ---------------------------------------------------------------------

def grade_to_class(grade_pct: float) -> str:
    """
    Ordnet eine Steigung (in %) einer der 3 Klassen zu, wie festgelegt:
        > 3%     -> "up"   (bergauf)
        -3..3%   -> "flat" (flach)
        < -3%    -> "down" (bergab)
    """
    if grade_pct > 3:
        return "up"
    if grade_pct < -3:
        return "down"
    return "flat"


def get_pace_for_segment(
    grade_pct: float,
    hr_zone: str,
    pace_hr_bins: dict,
    ef_factors: dict,
) -> float | None:
    """
    Liefert die EF-korrigierte Pace (sec/km) für EIN Streckensegment.

    Ablauf (das ist der Kern des ganzen Moduls):
    1. Steigung -> Klasse bestimmen ("up"/"flat"/"down")
    2. In pace_hr_bins[klasse][hr_zone] nachschauen -> Basis-Pace aus
       den historischen Trainingsdaten
    3. Mit dem passenden EF-Faktor für diese Klasse korrigieren

    Gibt None zurück, wenn für diese Kombination keine Trainingsdaten
    vorliegen (z.B. nie in Zone Z5 bergab gelaufen).
    """
    grade_class = grade_to_class(grade_pct)

    class_bins = pace_hr_bins.get(grade_class, {})
    base_pace = class_bins.get(hr_zone)

    if base_pace is None:
        return None

    factor = ef_factors.get(grade_class, 1.0)
    return apply_ef_factor(base_pace, factor)


# ---------------------------------------------------------------------
# Schritt 4: Gesamtzeit für die ganze Strecke bei einer HF-Zone
# ---------------------------------------------------------------------

def estimate_segments_for_zone(
    segments: "pd.DataFrame",
    hr_zone: str,
    pace_hr_bins: dict,
    ef_factors: dict,
) -> "pd.DataFrame":
    """
    Wendet get_pace_for_segment() auf JEDES Segment einer Strecke an.

    segments: DataFrame mit mindestens den Spalten
        - "grade_pct" (Steigung des Segments in %)
        - "start_m", "end_m" (Start/Ende des Segments in Metern)

    Gibt das DataFrame zurück, ergänzt um:
        - "pace_sec_per_km": die berechnete Pace
        - "data_available": True/False, ob für dieses Segment echte
          Trainingsdaten vorlagen (False = Fallback/Mittelwert genutzt)
    """
    import pandas as pd

    out = segments.copy()
    paces = []
    available = []

    for grade in out["grade_pct"]:
        pace = get_pace_for_segment(grade, hr_zone, pace_hr_bins, ef_factors)
        if pace is None:
            paces.append(None)
            available.append(False)
        else:
            paces.append(pace)
            available.append(True)

    out["pace_sec_per_km"] = paces
    out["data_available"] = available

    # Falls einzelne Segmente keine Daten hatten: mit dem Durchschnitt
    # der verfügbaren Segmente auffüllen, damit die Gesamtzeit trotzdem
    # berechnet werden kann (kein Segment soll "verschwinden").
    valid_paces = out["pace_sec_per_km"].dropna()
    if not valid_paces.empty:
        out["pace_sec_per_km"] = out["pace_sec_per_km"].fillna(valid_paces.mean())

    return out


def total_time_for_zone(segments_with_pace: "pd.DataFrame") -> float:
    """
    Summiert die Zeit (in Sekunden) über alle Segmente:
        zeit_segment = pace_sec_per_km * länge_segment_km

    segments_with_pace muss "pace_sec_per_km", "start_m", "end_m" enthalten
    (Ergebnis von estimate_segments_for_zone).
    """
    seg_length_km = (segments_with_pace["end_m"] - segments_with_pace["start_m"]) / 1000.0
    return float((segments_with_pace["pace_sec_per_km"] * seg_length_km).sum())


# ---------------------------------------------------------------------
# Schritt 5: Alle Zonen durchrechnen (Grundlage für "Zeit -> Zone")
# ---------------------------------------------------------------------

HR_ZONES = ["Z1", "Z2", "Z3", "Z4", "Z5"]


def compute_all_zone_times(
    segments: "pd.DataFrame",
    pace_hr_bins: dict,
    ef_factors: dict,
) -> dict:
    """
    Rechnet für JEDE der 5 HF-Zonen die Gesamtzeit der Strecke aus.

    Rückgabe: {
        "Z1": {"segments": <DataFrame mit Pace pro Segment>, "total_sec": <float>},
        "Z2": {...},
        ...
    }

    Das ist die Grundlage für die Zeit->Zone Umrechnung: wir müssen
    wissen, welche Zeit JEDE Zone ergeben würde, um dann die Zielzeit
    einordnen zu können.
    """
    result = {}
    for zone in HR_ZONES:
        seg_with_pace = estimate_segments_for_zone(segments, zone, pace_hr_bins, ef_factors)
        total_sec = total_time_for_zone(seg_with_pace)
        result[zone] = {"segments": seg_with_pace, "total_sec": total_sec}
    return result


# ---------------------------------------------------------------------
# Schritt 7: Zeit -> Zone (die "andere Richtung")
# ---------------------------------------------------------------------

def estimate_zone_for_target_time(
    segments: "pd.DataFrame",
    target_time_sec: float,
    pace_hr_bins: dict,
    ef_factors: dict,
) -> dict:
    """
    Findet zu einer gewünschten Zielzeit die passende HF-Zone.

    ABLAUF:
    1. compute_all_zone_times() liefert die Gesamtzeit für alle 5 Zonen.
       Da Z1 (locker) die langsamste und Z5 (hart) die schnellste Zeit
       ergibt, sind die 5 Zeiten der Größe nach sortiert.
    2. Liegt die Zielzeit SCHNELLER als die Z5-Zeit -> zu ambitioniert
       (schneller als die Person je in den Trainingsdaten belegt hat).
    3. Liegt die Zielzeit LANGSAMER als die Z1-Zeit -> ebenfalls eine
       Warnung (aber weniger kritisch, da Unterforderung nicht riskant ist).
    4. Sonst: die Zone mit der nächstgelegenen Gesamtzeit wählen und die
       Pace pro Segment so skalieren, dass die Summe exakt der Zielzeit
       entspricht (profilgewichtet: steile Abschnitte tragen mehr von der
       Korrektur als flache, weil dort in der Realität auch mehr
       Pace-Spielraum besteht).

    Rückgabe: {
        "is_too_ambitious": bool,
        "ambition_message": str,      # falls zu ambitioniert
        "chosen_zone": str,           # gewählte ODER nächstgelegene erreichbare Zone
        "segments": DataFrame,        # Pace pro Segment für chosen_zone
    }
    WICHTIG: auch wenn is_too_ambitious=True ist, sind chosen_zone und
    segments NICHT None - sie enthalten dann die nächstgelegene
    tatsächlich erreichbare Zone (Z5 bei zu schnellem, Z1 bei zu
    langsamem Ziel), damit die App (Karte, Slider, Export) trotz der
    Warnung weiter nutzbar bleibt, statt komplett zu stoppen.
    """
    all_zones = compute_all_zone_times(segments, pace_hr_bins, ef_factors)

    # Z1 = langsamste Zeit, Z5 = schnellste Zeit (siehe Doku oben)
    fastest_time = all_zones["Z5"]["total_sec"]
    slowest_time = all_zones["Z1"]["total_sec"]

    # Fall 1: zu schnelles Ziel (schneller als die eigene Bestleistung Z5)
    if target_time_sec < fastest_time:
        margin_pct = (fastest_time - target_time_sec) / fastest_time * 100
        return {
            "is_too_ambitious": True,
            "ambition_message": (
                f"Diese Zielzeit ist sehr ambitioniert: selbst in deiner "
                f"intensivsten bisherigen Trainingszone (Z5) würdest du für "
                f"diese Strecke etwa {fastest_time/60:.1f} Minuten brauchen - "
                f"das ist {margin_pct:.0f}% langsamer als dein Ziel. Diese "
                f"Schätzung liegt außerhalb deiner bisherigen Trainingsdaten. "
                f"Die Karte unten zeigt deshalb die Pace für deine schnellste "
                f"bisherige Trainingszone (Z5) als Annäherung."
            ),
            # Fallback: die schnellste tatsächlich belegte Zone anzeigen,
            # statt gar nichts anzuzeigen - die App bleibt so nutzbar.
            "chosen_zone": "Z5",
            "segments": all_zones["Z5"]["segments"],
        }

    # Fall 2: sehr langsames Ziel (langsamer als die eigene lockerste Zone Z1)
    if target_time_sec > slowest_time:
        return {
            "is_too_ambitious": True,
            "ambition_message": (
                f"Diese Zielzeit ist langsamer als deine bisherige lockerste "
                f"Trainingszone (Z1, ca. {slowest_time/60:.1f} Minuten für diese "
                f"Strecke). Die Schätzung liegt außerhalb deiner bisherigen "
                f"Trainingsdaten. Die Karte unten zeigt deshalb die Pace für "
                f"deine lockerste bisherige Trainingszone (Z1) als Annäherung."
            ),
            # Fallback: die langsamste tatsächlich belegte Zone anzeigen,
            # statt gar nichts anzuzeigen - die App bleibt so nutzbar.
            "chosen_zone": "Z1",
            "segments": all_zones["Z1"]["segments"],
        }

    # Fall 3: Zielzeit liegt im normalen Bereich - nächstgelegene Zone wählen
    chosen_zone = min(
        HR_ZONES,
        key=lambda z: abs(all_zones[z]["total_sec"] - target_time_sec),
    )
    achieved_time = all_zones[chosen_zone]["total_sec"]
    base_segments = all_zones[chosen_zone]["segments"]

    final_segments = _scale_pace_to_target_time(
        base_segments, achieved_time, target_time_sec
    )

    return {
        "is_too_ambitious": False,
        "ambition_message": "",
        "chosen_zone": chosen_zone,
        "segments": final_segments,
    }


def _scale_pace_to_target_time(
    segments_with_pace: "pd.DataFrame",
    achieved_time_sec: float,
    target_time_sec: float,
    profile_weight: float = 8.0,
) -> "pd.DataFrame":
    """
    Skaliert die Pace pro Segment so, dass die Gesamtzeit exakt der
    Zielzeit entspricht - aber NICHT gleichmäßig auf alle Meter verteilt,
    sondern gewichtet nach Steigung: steile Abschnitte (größer |grade|)
    tragen mehr von der Korrektur als Flachstücke.

    Das ist dieselbe Idee wie vorher: auf einem steilen Anstieg gibt es in
    der Realität mehr Spielraum, die Pace zu variieren, als auf einem
    flachen Stück.
    """
    out = segments_with_pace.copy()
    seg_length_km = (out["end_m"] - out["start_m"]) / 1000.0

    diff_sec = target_time_sec - achieved_time_sec  # >0: muss langsamer werden

    weight = 1.0 + (out["grade_pct"].abs() / profile_weight)
    weighted_length = seg_length_km * weight
    total_weighted_length = weighted_length.sum()

    if total_weighted_length <= 0:
        return out

    correction_per_km = (diff_sec / total_weighted_length) * weight
    out["pace_sec_per_km"] = out["pace_sec_per_km"] + correction_per_km
    out["pace_sec_per_km"] = out["pace_sec_per_km"].clip(lower=120)  # Sicherheitsnetz
    return out
