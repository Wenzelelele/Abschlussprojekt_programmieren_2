"""
pace_model.py
-------------
Effizienz-Korrektur aus den 3 Efficiency-Factor-Werten (bergauf/flach/
bergab) und Pace-Schaetzung pro Streckensegment.

EF = Geschwindigkeit (m/min) / Herzfrequenz (bpm), hoeher = effizienter.
Wir vergleichen die 3 EF-Werte nur UNTEREINANDER (nicht gegen einen
externen Sollwert), um zu sehen, in welchem Gelaende die Person relativ
zu sich selbst staerker/schwaecher ist. Der Faktor wird dann auf die
Basis-Pace aus den Bins multipliziert (genauer: durch den Faktor geteilt,
siehe apply_ef_factor).
"""


def compute_ef_factors(ef_up: float, ef_flat: float, ef_down: float) -> dict:
    """
    Berechnet für jede Geländeart einen relativen Stärke-Faktor,
    indem der jeweilige EF durch den Durchschnitt aller drei EF-Werte
    geteilt wird.

    Rückgabe: {"up": factor, "flat": factor, "down": factor}
    Faktor > 1.0 = überdurchschnittlich stark, < 1.0 = unterdurchschnittlich.
    """
    avg_ef = (ef_up + ef_flat + ef_down) / 3.0

    if avg_ef <= 0:
        # ungueltige Eingabe, sollte nie 0/negativ sein
        return {"up": 1.0, "flat": 1.0, "down": 1.0}

    return {
        "up": ef_up / avg_ef,
        "flat": ef_flat / avg_ef,
        "down": ef_down / avg_ef,
    }


def apply_ef_factor(base_pace_sec_per_km: float, ef_factor: float) -> float:
    """
    Wendet einen EF-Stärke-Faktor auf eine Basis-Pace an.

    Pace ist in sec/km - kleinere Zahl = schneller. Ein Faktor > 1 soll
    die Pace schneller machen, deshalb wird DURCH den Faktor geteilt statt
    multipliziert: neue_pace = basis_pace / ef_factor.
    """
    if ef_factor <= 0:
        return base_pace_sec_per_km
    return base_pace_sec_per_km / ef_factor


# ---------------------------------------------------------------------
# Schritt 3: Steigungsklasse bestimmen + Pace-Lookup mit EF-Korrektur
# ---------------------------------------------------------------------

def grade_to_class(grade_pct: float) -> str:
    """
    Ordnet eine Steigung (in %) einer der 3 Klassen zu:
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
    Liefert die EF-korrigierte Pace (sec/km) für EIN Streckensegment:
    Steigung -> Klasse -> Basis-Pace aus pace_hr_bins -> EF-Korrektur.

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

    Gibt das DataFrame zurück, ergänzt um:
        - "pace_sec_per_km": die berechnete Pace
        - "data_available": ob fuer dieses Segment echte Trainingsdaten
          vorlagen (False = Fallback/Mittelwert genutzt)
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

    # fehlende Segmente mit Durchschnitt der vorhandenen auffuellen,
    # damit kein Segment aus der Gesamtzeit-Berechnung rausfaellt
    valid_paces = out["pace_sec_per_km"].dropna()
    if not valid_paces.empty:
        out["pace_sec_per_km"] = out["pace_sec_per_km"].fillna(valid_paces.mean())

    return out


def total_time_for_zone(segments_with_pace: "pd.DataFrame") -> float:
    """
    Summiert die Zeit (in Sekunden) über alle Segmente:
    zeit_segment = pace_sec_per_km * länge_segment_km.
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

    Rückgabe: {"Z1": {"segments": DataFrame, "total_sec": float}, "Z2": {...}, ...}
    Grundlage fuer die Zeit->Zone Umrechnung unten.
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

    Z1 ist die langsamste, Z5 die schnellste Zone. Liegt die Zielzeit
    schneller als Z5, ist sie zu ambitioniert (Warnung). Liegt sie
    langsamer als Z1, wird sie einfach bei Z1 gedeckelt (keine Warnung,
    Unterforderung ist nicht riskant). Sonst wird die naechstgelegene
    Zone gewaehlt und die Pace pro Segment profilgewichtet auf die
    Zielzeit skaliert (steile Abschnitte tragen mehr von der Korrektur).

    Rückgabe: {
        "is_too_ambitious": bool,
        "ambition_message": str,      # falls zu ambitioniert
        "chosen_zone": str,           # gewählte ODER nächstgelegene erreichbare Zone
        "segments": DataFrame,        # Pace pro Segment für chosen_zone
    }
    chosen_zone/segments sind auch bei is_too_ambitious=True nie None,
    damit die App (Karte, Slider, Export) trotzdem nutzbar bleibt.
    """
    all_zones = compute_all_zone_times(segments, pace_hr_bins, ef_factors)

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
            "chosen_zone": "Z5",
            "segments": all_zones["Z5"]["segments"],
        }

    # Fall 2: sehr langsames Ziel (langsamer als die eigene lockerste Zone Z1)
    # - keine Warnung, da Unterforderung nicht riskant ist. Die Prognose
    # wird einfach still bei Z1 gedeckelt.
    if target_time_sec > slowest_time:
        return {
            "is_too_ambitious": False,
            "ambition_message": "",
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
    Zielzeit entspricht - gewichtet nach Steigung, damit steile
    Abschnitte mehr von der Korrektur tragen als flache (dort ist in
    der Realitaet auch mehr Pace-Spielraum).
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
