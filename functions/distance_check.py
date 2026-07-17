"""
distance_check.py
------------------
Prüft, ob eine hochgeladene Strecke im Vergleich zur bisherigen
Lauf-Historie unrealistisch lang ist (macht sonst keine sinnvolle
Pace-Vorhersage möglich).

Schwellwert: 2.5-faches der bisherigen Maximaldistanz.
"""


AMBITION_DISTANCE_FACTOR = 2.5


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
