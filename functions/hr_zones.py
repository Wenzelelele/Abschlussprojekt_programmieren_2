"""
hr_zones.py
-----------
Bestimmung der HF-Zonen (Z1-Z5): drei Methoden zur Grenzen-Bestimmung
(manuell / max_hr / Alter) und Zuordnung einzelner Messwerte. Die drei
get_zone_boundaries_*-Funktionen liefern dasselbe Dict-Format, sodass
hr_to_zone die gewaehlte Methode nicht kennen muss.
"""

import math

# Prozentgrenzen der Zonen bezogen auf max_hr:
# Z1 < 60%, Z2 60-70%, Z3 70-80%, Z4 80-90%, Z5 >= 90%
ZONE_PCT_BOUNDS = [0.60, 0.70, 0.80, 0.90]

ZONE_NAMES = ["Z1", "Z2", "Z3", "Z4", "Z5"]


def estimate_max_hr_tanaka(age: int) -> float:
    """
    Schaetzt max_hr aus dem Alter (Tanaka-Formel: 208 - 0.7 * Alter).

    Input:  age - Alter in Jahren
    Output: geschaetzte max_hr in bpm
    """
    return 208.0 - 0.7 * age


def _bounds_to_zone_dict(bounds: list[float]) -> dict:
    """Baut aus 4 aufsteigenden Trennwerten das Zonen-Dict Z1-Z5."""
    edges = [0.0, *bounds, math.inf]
    return {zone: (edges[i], edges[i + 1]) for i, zone in enumerate(ZONE_NAMES)}


def get_zone_boundaries_manual(bounds: list[float]) -> dict:
    """
    Baut Zonen-Grenzen aus 4 manuell eingegebenen bpm-Trennwerten.

    Input:  bounds - 4 bpm-Werte, aufsteigend sortiert
    Output: {"Z1": (0, b1), "Z2": (b1, b2), ..., "Z5": (b4, inf)}
    """
    if len(bounds) != 4:
        raise ValueError(f"Es werden genau 4 Trennwerte erwartet, nicht {len(bounds)}.")
    if sorted(bounds) != list(bounds):
        raise ValueError("Die Trennwerte muessen aufsteigend sortiert sein.")
    return _bounds_to_zone_dict(list(bounds))


def get_zone_boundaries_maxhr(max_hr: float) -> dict:
    """
    Baut Zonen-Grenzen als %-Anteile von max_hr
    (Z1<60%, Z2 60-70%, Z3 70-80%, Z4 80-90%, Z5>=90%).

    Input:  max_hr - maximale Herzfrequenz in bpm
    Output: gleiches Format wie get_zone_boundaries_manual
    """
    return _bounds_to_zone_dict([pct * max_hr for pct in ZONE_PCT_BOUNDS])


def get_zone_boundaries_age(age: int) -> dict:
    """
    Schaetzt zuerst max_hr (Tanaka), ruft dann get_zone_boundaries_maxhr auf.

    Input:  age - Alter in Jahren
    Output: gleiches Format wie get_zone_boundaries_manual
    """
    return get_zone_boundaries_maxhr(estimate_max_hr_tanaka(age))


def hr_to_zone(hr: float, zone_boundaries: dict) -> str:
    """
    Ordnet eine einzelne HF-Messung ihrer Zone zu (reiner Lookup,
    kennt keine der drei Methoden - nimmt nur fertige Grenzen entgegen).

    Input:  hr - gemessene Herzfrequenz in bpm
            zone_boundaries - Dict aus einer der drei Funktionen oben
    Output: "Z1" bis "Z5"
    """
    for zone, (lower, upper) in zone_boundaries.items():
        if lower <= hr < upper:
            return zone
    # Einziger Fall, der durchfallen kann: hr < 0 (Messfehler) -> Z1,
    # analog zur np.clip-Idee, Ausreisser an den Rand zu druecken.
    return "Z1"
