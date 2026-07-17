"""
distance_check.py
------------------
Prüft, ob eine hochgeladene Strecke im Vergleich zur bisherigen
Lauf-Historie unrealistisch lang oder steil ist (macht sonst keine
sinnvolle Pace-Vorhersage möglich).

Schwellwert: 2.5-faches der bisherigen Maximaldistanz bzw. -Höhenmeter.
"""


AMBITION_DISTANCE_FACTOR = 2.5
AMBITION_ELEVATION_FACTOR = 2.5


def check_distance_ambition(route_distance_km: float, max_distance_km: float) -> dict:
    """
    Vergleicht die Streckenlänge der hochgeladenen GPX mit der bisherigen
    maximalen Laufdistanz (aus den Trainingsdaten).

    Rückgabe: {
        "is_too_ambitious": bool,
        "threshold_km": float,       # ab welcher Distanz es "zu viel" wäre
        "ratio": float,              # Strecke / bisherige Maximaldistanz
        "message": str,              # fertige Fehlermeldung, falls zu ambitioniert
    }
    """
    if max_distance_km <= 0:
        # keine Trainingsdaten -> koennen wir nicht bewerten
        return {
            "is_too_ambitious": False,
            "threshold_km": None,
            "ratio": None,
            "message": (
                "Keine bisherige Maximaldistanz in den Trainingsdaten gefunden - "
                "die Einschätzung der Streckenlänge ist daher nicht möglich."
            ),
        }

    threshold_km = max_distance_km * AMBITION_DISTANCE_FACTOR
    ratio = route_distance_km / max_distance_km
    is_too_ambitious = route_distance_km > threshold_km

    message = ""
    if is_too_ambitious:
        message = (
            f"Diese Strecke ist {route_distance_km:.1f} km lang - das ist "
            f"{ratio:.1f}-mal so weit wie deine bisherige längste Strecke "
            f"({max_distance_km:.1f} km). Das liegt deutlich außerhalb deiner "
            f"bisherigen Erfahrung, eine verlässliche Pace-Vorhersage ist hier "
            f"nicht möglich."
        )

    return {
        "is_too_ambitious": is_too_ambitious,
        "threshold_km": threshold_km,
        "ratio": ratio,
        "message": message,
    }


def check_elevation_ambition(route_ascent_m: float, max_elevation_m: float) -> dict:
    """
    Vergleicht den Aufstieg der hochgeladenen GPX mit dem bisherigen
    maximalen Aufstieg (aus den Trainingsdaten). Gleiches Prinzip wie
    check_distance_ambition, nur auf Höhenmeter statt Kilometer.

    Rückgabe: {
        "is_too_ambitious": bool,
        "threshold_m": float,        # ab welchem Aufstieg es "zu viel" wäre
        "ratio": float,              # Aufstieg / bisheriger maximaler Aufstieg
        "message": str,              # fertige Fehlermeldung, falls zu ambitioniert
    }
    """
    if max_elevation_m <= 0:
        # keine Trainingsdaten -> koennen wir nicht bewerten
        return {
            "is_too_ambitious": False,
            "threshold_m": None,
            "ratio": None,
            "message": (
                "Keine bisherigen Höhenmeter in den Trainingsdaten gefunden - "
                "die Einschätzung der Höhenmeter ist daher nicht möglich."
            ),
        }

    threshold_m = max_elevation_m * AMBITION_ELEVATION_FACTOR
    ratio = route_ascent_m / max_elevation_m
    is_too_ambitious = route_ascent_m > threshold_m

    message = ""
    if is_too_ambitious:
        message = (
            f"Diese Strecke hat {route_ascent_m:.0f} Höhenmeter - das ist "
            f"{ratio:.1f}-mal so viel wie dein bisher stärkster Aufstieg "
            f"({max_elevation_m:.0f} m). Das liegt deutlich außerhalb deiner "
            f"bisherigen Erfahrung, eine verlässliche Pace-Vorhersage ist hier "
            f"nicht möglich."
        )

    return {
        "is_too_ambitious": is_too_ambitious,
        "threshold_m": threshold_m,
        "ratio": ratio,
        "message": message,
    }
