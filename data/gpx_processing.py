"""
gpx_processing.py
------------------
GPX einlesen und Distanz/Höhe/Steigung pro Segment berechnen.
"""


import math
from dataclasses import dataclass

import gpxpy
import numpy as np
import pandas as pd


EARTH_RADIUS_M = 6371000.0


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Distanz zwischen zwei Koordinaten in Metern (Haversine-Formel)."""
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lambda = math.radians(lon2 - lon1)
    a = (
        math.sin(d_phi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    )
    return 2 * EARTH_RADIUS_M * math.asin(min(1.0, math.sqrt(a)))


@dataclass
class RouteData:
    """Ergebnis des GPX-Parsings: ein DataFrame mit einer Zeile pro Trackpunkt."""

    points: pd.DataFrame  # lat, lon, ele, dist_m (cum.), seg_dist_m, grade_pct
    total_distance_m: float
    total_ascent_m: float
    total_descent_m: float
    name: str


def parse_gpx(file_obj, smoothing_window: int = 5) -> RouteData:
    """
    Liest eine GPX-Datei und gibt ein RouteData-Objekt zurück.

    smoothing_window glättet die Höhe, um GPS-Rauschen bei der
    Steigungsberechnung zu reduzieren.
    """
    gpx = gpxpy.parse(file_obj)

    rows = []
    for track in gpx.tracks:
        for segment in track.segments:
            for pt in segment.points:
                rows.append(
                    {
                        "lat": pt.latitude,
                        "lon": pt.longitude,
                        "ele": pt.elevation if pt.elevation is not None else np.nan,
                    }
                )

    if not rows:
        # manche GPX-Dateien haben Wegpunkte statt Tracks
        for wpt in gpx.waypoints:
            rows.append({"lat": wpt.latitude, "lon": wpt.longitude, "ele": wpt.elevation})

    if len(rows) < 2:
        raise ValueError("GPX-Datei enthält keine verwertbare Streckendaten (Track/Segmente).")

    df = pd.DataFrame(rows)

    # Höhe glätten, um Steigungs-Rauschen zu dämpfen
    df["ele"] = df["ele"].interpolate(limit_direction="both")
    df["ele_smooth"] = (
        df["ele"].rolling(window=smoothing_window, center=True, min_periods=1).mean()
    )

    # Distanz zwischen aufeinanderfolgenden Punkten
    seg_dist = [0.0]
    for i in range(1, len(df)):
        d = haversine_m(
            df.loc[i - 1, "lat"], df.loc[i - 1, "lon"], df.loc[i, "lat"], df.loc[i, "lon"]
        )
        seg_dist.append(d)
    df["seg_dist_m"] = seg_dist
    df["dist_m"] = df["seg_dist_m"].cumsum()

    # Höhenänderung & Steigung pro Segment
    df["ele_diff"] = df["ele_smooth"].diff().fillna(0.0)
    with np.errstate(divide="ignore", invalid="ignore"):
        grade = np.where(
            df["seg_dist_m"] > 0.5,  # zu kurze Segmente ignorieren -> Rauschen
            (df["ele_diff"] / df["seg_dist_m"].replace(0, np.nan)) * 100.0,
            0.0,
        )
    df["grade_pct"] = pd.Series(grade).clip(-40, 40).fillna(0.0)

    total_distance_m = float(df["dist_m"].iloc[-1])
    ascent = float(df.loc[df["ele_diff"] > 0, "ele_diff"].sum())
    descent = float(-df.loc[df["ele_diff"] < 0, "ele_diff"].sum())

    name = "Strecke"
    if gpx.tracks and gpx.tracks[0].name:
        name = gpx.tracks[0].name
    elif gpx.name:
        name = gpx.name

    return RouteData(
        points=df,
        total_distance_m=total_distance_m,
        total_ascent_m=ascent,
        total_descent_m=descent,
        name=name,
    )


def resample_route(route: RouteData, segment_length_m: float = 100.0) -> pd.DataFrame:
    """
    Aggregiert die Rohpunkte zu gleichlangen Abschnitten (z.B. alle 100 m)
    fuer gleichmaessige Slider-Schritte statt einem Schritt pro GPS-Punkt.

    Spalten: start_m, end_m, mid_m, lat, lon, grade_pct, ele.
    """
    df = route.points
    total = route.total_distance_m
    n_segments = max(1, int(math.ceil(total / segment_length_m)))

    bin_edges = np.linspace(0, total, n_segments + 1)
    bin_idx = np.digitize(df["dist_m"], bin_edges) - 1
    bin_idx = np.clip(bin_idx, 0, n_segments - 1)

    out_rows = []
    for b in range(n_segments):
        mask = bin_idx == b
        if not mask.any():
            # leerer Bin (kurze Strecke) -> Punkt interpolieren
            mid = (bin_edges[b] + bin_edges[b + 1]) / 2
            lat = np.interp(mid, df["dist_m"], df["lat"])
            lon = np.interp(mid, df["dist_m"], df["lon"])
            ele = np.interp(mid, df["dist_m"], df["ele_smooth"])
            grade = 0.0
        else:
            sub = df.loc[mask]
            lat = sub["lat"].mean()
            lon = sub["lon"].mean()
            ele = sub["ele_smooth"].mean()
            # Steigung: Höhendifferenz Start->Ende / Distanz
            ele_start = sub["ele_smooth"].iloc[0]
            ele_end = sub["ele_smooth"].iloc[-1]
            dist_span = max(sub["seg_dist_m"].sum(), 1e-6)
            grade = ((ele_end - ele_start) / dist_span) * 100.0

        out_rows.append(
            {
                "start_m": bin_edges[b],
                "end_m": bin_edges[b + 1],
                "mid_m": (bin_edges[b] + bin_edges[b + 1]) / 2,
                "lat": lat,
                "lon": lon,
                "ele": ele,
                "grade_pct": np.clip(grade, -40, 40),
            }
        )

    return pd.DataFrame(out_rows)
