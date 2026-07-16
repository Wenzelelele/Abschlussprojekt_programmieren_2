"""
hr_zones.py
-----------
Bestimmung der HF-Zonen (Z1-Z5): drei Methoden zur Grenzen-Bestimmung
(manuell / max_hr / Alter) und Zuordnung einzelner Messwerte.
"""


def estimate_max_hr_tanaka(age: int) -> float:
    """
    Schätzt max_hr aus dem Alter (Tanaka-Formel).

    Input:  age - Alter in Jahren
    Output: geschätzte max_hr in bpm
    """
    raise NotImplementedError("TODO: 208 - 0.7 * age")


def get_zone_boundaries_manual(bounds: list[float]) -> dict:
    """
    Baut Zonen-Grenzen aus 4 manuell eingegebenen bpm-Trennwerten.

    Input:  bounds - 4 bpm-Werte, aufsteigend sortiert
    Output: {"Z1": (0, b1), "Z2": (b1, b2), ..., "Z5": (b4, inf)}
    """
    raise NotImplementedError("TODO: Tupel-Paare aus bounds bauen")


def get_zone_boundaries_maxhr(max_hr: float) -> dict:
    """
    Baut Zonen-Grenzen als %-Anteile von max_hr
    (Z1<60%, Z2 60-70%, Z3 70-80%, Z4 80-90%, Z5>=90%).

    Input:  max_hr - maximale Herzfrequenz in bpm
    Output: gleiches Format wie get_zone_boundaries_manual
    """
    raise NotImplementedError("TODO: Prozentgrenzen mit max_hr multiplizieren")


def get_zone_boundaries_age(age: int) -> dict:
    """
    Schätzt zuerst max_hr (Tanaka), ruft dann get_zone_boundaries_maxhr auf.

    Input:  age - Alter in Jahren
    Output: gleiches Format wie get_zone_boundaries_manual
    """
    raise NotImplementedError(
        "TODO: estimate_max_hr_tanaka + get_zone_boundaries_maxhr kombinieren"
    )


def hr_to_zone(hr: float, zone_boundaries: dict) -> str:
    """
    Ordnet eine einzelne HF-Messung ihrer Zone zu.

    Input:  hr - gemessene Herzfrequenz in bpm
            zone_boundaries - Dict aus einer der drei Funktionen oben
    Output: "Z1" bis "Z5"
    """
    raise NotImplementedError("TODO: passendes Intervall im Dict finden")
