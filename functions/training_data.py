"""
training_data.py
-----------------
TrainingData-Klasse: verwaltet alle Runs einer Person, orchestriert
die Auswertung und liefert die Werte fuer session_state. Die Klasse
rechnet selbst nichts Fachliches - sie delegiert an die reinen
Funktionen in efficiency.py und haelt nur den Zustand zusammen.
"""

import pandas as pd

from functions.efficiency import calc_efficiency_factor


class TrainingData:
    """
    Attribute:
        person_id: str          - Referenz auf die Person (username)
        df: pd.DataFrame        - alle Runs gepoolt, inkl. run_id-Spalte
        ef_factors: dict        - {"up": .., "flat": .., "down": ..}
        pace_hr_bins: dict      - {"up": {"Z1": .., ...}, ...}
        max_distance_km: float  - laengster einzelner Run
        max_elevation_m: float  - meiste Hoehenmeter in einer Aktivitaet
        n_runs: int             - Anzahl erfolgreich verarbeiteter Runs
    """

    def __init__(self, person_id: str):
        self.person_id = person_id
        self.df = pd.DataFrame()
        self.ef_factors: dict = {}
        self.pace_hr_bins: dict = {}
        self.max_distance_km = 0.0
        self.max_elevation_m = 0.0
        self.n_runs = 0

    def add_run(self, run_df: pd.DataFrame) -> None:
        """
        Fuegt einen einzelnen, bereits preprocessed + terrain-
        klassifizierten Run hinzu.

        Input:  run_df - df eines Laufs, MUSS eine eindeutige
                run_id-Spalte haben (ein Wert pro Run)
        Output: None (veraendert self.df)
        """
        if "run_id" not in run_df.columns:
            raise ValueError("run_df braucht eine run_id-Spalte.")

        new_ids = set(run_df["run_id"])
        if len(new_ids) != 1:
            raise ValueError("Ein Run darf nur genau eine run_id enthalten.")
        if not self.df.empty and new_ids & set(self.df["run_id"]):
            raise ValueError(f"run_id {new_ids.pop()!r} existiert bereits.")

        self.df = pd.concat([self.df, run_df], ignore_index=True)

    def compute_all(self) -> None:
        """
        Berechnet ef_factors, pace_hr_bins, max_distance_km und
        max_elevation_m aus self.df.

        max_distance_km / max_elevation_m sind bewusst PRO RUN
        aggregiert (groupby run_id) und dann das Maximum ueber alle
        Runs - nicht die Summe aller Runs, denn distance_check.py
        vergleicht eine geplante Route mit dem laengsten EINZELNEN Lauf.

        Output: None (setzt self.-Attribute)
        """
        if self.df.empty:
            return

        self.ef_factors, self.pace_hr_bins = calc_efficiency_factor(self.df)

        per_run = self.df.groupby("run_id")
        dist_km_per_run = per_run["dist_delta_m"].sum() / 1000.0
        # Aufstieg = nur positive Hoehenaenderungen aufsummieren
        ascent_per_run = per_run["ele_delta_m"].apply(lambda s: s.clip(lower=0).sum())

        self.max_distance_km = float(dist_km_per_run.max())
        self.max_elevation_m = float(ascent_per_run.max())
        self.n_runs = self.df["run_id"].nunique()
