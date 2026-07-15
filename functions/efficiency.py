"""
efficiency.py
-------------
GAP-Pace-Berechnung und Efficiency-Factor-Auswertung pro Geländeart
und HF-Zone. Kernstück des Trainingsdaten-Tabs.
"""

import pandas as pd


def calc_gap_pace(pace: float, grade_pct: float) -> float:
    """
    Rechnet reale Pace in steigungsbereinigte GAP-Pace um.

    Input:  pace - reale Pace in sec/km
            grade_pct - Steigung in Prozent
    Output: gap_pace in sec/km
    """
    raise NotImplementedError("TODO: Steigungskorrektur-Formel anwenden")


def calc_efficiency_factor(df: pd.DataFrame) -> tuple[dict, dict]:
    """
    Berechnet aus allen gepoolten Runs: 1) einen EF pro Geländeart,
    2) eine Pace-Tabelle pro Geländeart x HF-Zone.

    Input:  df - preprocessed + terrain-klassifizierter DataFrame
             aller Runs (mit run_id, terrain, hr_zone, gap_pace)
    Output: (ef_factors, pace_hr_bins)
             ef_factors: {"up": .., "flat": .., "down": ..}
             pace_hr_bins: {"up": {"Z1": .., ...}, "flat": {...}, "down": {...}}
    """
    raise NotImplementedError(
        "TODO: groupby(['terrain','hr_zone']) für pace_hr_bins, groupby('terrain') für ef_factors"
    )
