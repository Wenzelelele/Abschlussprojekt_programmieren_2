"""
training_data.py
-----------------
TrainingData-Klasse: verwaltet alle Runs einer Person, orchestriert
die Pipeline, liefert die Werte für session_state.
"""

import pandas as pd


class TrainingData:
    """
    Attribute:
        person_id: str          - Referenz auf die Person (username)
        df: pd.DataFrame        - alle Runs gepoolt, inkl. run_id-Spalte
        ef_factors: dict        - {"up": .., "flat": .., "down": ..}
        pace_hr_bins: dict      - {"up": {"Z1": .., ...}, ...}
        max_distance_km: float  - längster einzelner Run
        max_elevation_m: float  - meiste Höhenmeter in einer Aktivität
    """

    def __init__(self, person_id: str):
        raise NotImplementedError(
            "TODO: Attribute initialisieren (leeres df, leere dicts)"
        )

    def add_run(self, run_df: pd.DataFrame) -> None:
        """
        Fügt einen einzelnen, bereits verarbeiteten Run hinzu.

        Input:  run_df - df eines Laufs, MUSS eindeutige run_id-Spalte haben
        Output: None (verändert self.df)
        """
        raise NotImplementedError("TODO: pd.concat auf self.df")

    def compute_all(self) -> None:
        """
        Berechnet ef_factors, pace_hr_bins, max_distance_km,
        max_elevation_m aus self.df.

        Output: None (setzt self.-Attribute)
        """
        raise NotImplementedError(
            "TODO: calc_efficiency_factor + groupby('run_id') für die zwei max-Werte"
        )
