"""
efficiency.py
-------------
GAP-Pace-Berechnung und Efficiency-Factor-Auswertung pro Gelaendeart
und HF-Zone. Kernstueck des Trainingsdaten-Tabs: hier entstehen die
Werte, die pace_model.py spaeter fuer die Routen-Vorhersage konsumiert.
"""

import numpy as np
import pandas as pd

# Minetti-Polynom gilt nur fuer Steigungen bis +-40% (dort wurde es
# gemessen) - passt zum +-40%-Clipping in gpx_processing.py.
MAX_GRADE_FRACTION = 0.40

# Energiekosten des Laufens in der Ebene laut Minetti: 3.6 J/(kg*m).
_FLAT_ENERGY_COST = 3.6


def calc_gap_pace(pace: float, grade_pct: float) -> float:
    """
    Rechnet reale Pace in steigungsbereinigte GAP-Pace um.

    FORMEL: Minetti et al. (2002) haben die metabolischen Energiekosten
    des Laufens als Polynom der Steigung i (als Bruchteil, z.B. 0.05
    fuer 5%) gemessen:

        C(i) = 155.4*i^5 - 30.4*i^4 - 43.3*i^3 + 46.3*i^2 + 19.5*i + 3.6

    GAP beantwortet die Frage "welcher Pace in der Ebene entspricht
    dieser Anstrengung?". Kostet ein Meter bergauf das r-fache eines
    Meters in der Ebene (r = C(i)/C(0)), dann entspricht die gelaufene
    Pace einer um den Faktor r schnelleren Flach-Pace:

        gap_pace = pace / r = pace * C(0) / C(i)

    Wir nutzen Minetti statt einer einfachen %-Korrektur, weil das
    Polynom bergauf und bergab asymmetrisch korrekt abbildet (bergab
    ist bis ca. -20% BILLIGER als flach, danach wieder teurer) - eine
    lineare Korrektur bekommt genau das nicht hin.

    Input:  pace - reale Pace in sec/km
            grade_pct - Steigung in Prozent
    Output: gap_pace in sec/km

    Funktioniert dank NumPy-Operationen auch elementweise auf ganzen
    Series/Arrays (so wird sie in preprocess vektorisiert aufgerufen).
    """
    i = np.clip(
        np.asarray(grade_pct, dtype=float) / 100.0,
        -MAX_GRADE_FRACTION,
        MAX_GRADE_FRACTION,
    )
    cost = (
        155.4 * i**5
        - 30.4 * i**4
        - 43.3 * i**3
        + 46.3 * i**2
        + 19.5 * i
        + _FLAT_ENERGY_COST
    )
    gap = pace * _FLAT_ENERGY_COST / cost
    # Skalar rein -> Skalar raus (np.clip macht aus floats 0-d-Arrays)
    return float(gap) if np.ndim(gap) == 0 else gap


def calc_efficiency_factor(df: pd.DataFrame) -> tuple[dict, dict]:
    """
    Berechnet aus allen gepoolten Runs: 1) einen EF pro Gelaendeart,
    2) eine Pace-Tabelle pro Gelaendeart x HF-Zone.

    EF ist hier wie in pace_model.py definiert (Standard-Lauf-Metrik):
        EF = Geschwindigkeit (m/min) / Herzfrequenz (bpm)
    berechnet auf Basis der GAP-Geschwindigkeit, damit der Wert nicht
    davon abhaengt, wie steil die jeweiligen Abschnitte zufaellig waren.
    Hoeherer EF = schneller bei gleicher HF = effizienter.

    Input:  df - preprocessed + terrain-klassifizierter DataFrame
             aller Runs (Spalten: terrain, hr, hr_zone, gap_pace, run_id)
    Output: (ef_factors, pace_hr_bins)
             ef_factors: {"up": .., "flat": .., "down": ..}
             pace_hr_bins: {"up": {"Z1": .., ...}, "flat": {...}, "down": {...}}
             Kombinationen ohne Datenpunkte fehlen einfach im Dict -
             get_pace_for_segment in pace_model.py faengt das per .get() ab.
    """
    # Nur physikalisch sinnvolle Zeilen: hr=0 wuerde durch die Division
    # einen unendlichen EF erzeugen und den Mittelwert zerstoeren.
    valid = df[(df["hr"] > 0) & (df["gap_pace"] > 0)]
    if valid.empty:
        return {}, {}

    speed_m_per_min = 60000.0 / valid["gap_pace"]
    ef_per_point = speed_m_per_min / valid["hr"]

    ef_factors = {
        terrain: float(ef)
        for terrain, ef in ef_per_point.groupby(valid["terrain"]).mean().items()
    }

    pace_hr_bins: dict = {}
    zone_means = valid.groupby(["terrain", "hr_zone"])["gap_pace"].mean()
    for (terrain, zone), mean_pace in zone_means.items():
        pace_hr_bins.setdefault(terrain, {})[zone] = float(mean_pace)

    return ef_factors, pace_hr_bins
