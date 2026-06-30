"""
distance_check.py
------------------
Schritt 6: Prueft, ob eine hochgeladene Strecke im Vergleich zur
bisherigen Lauf-Historie unrealistisch lang ist.

GRUNDIDEE:
Wenn jemand bisher maximal 10 km gelaufen ist und eine 100 km-Strecke
hochlaedt, macht eine Pace-Vorhersage wenig Sinn - wir haben schlicht
keine Trainingsdaten, die zeigen, wie sich der Koerper bei dieser
Belastung verhaelt (Ermuedung nach 3-4 Stunden ist etwas komplett
anderes als nach 50 Minuten).

Schwellwert: 2.5-faches der bisherigen Maximaldistanz.
Beispiel: bisher max. 10 km gelaufen -> ab 25 km Streckenlaenge kommt
die Warnung.
"""


AMBITION_DISTANCE_FACTOR = 2.5


def check_distance_ambition(route_distance_km: float, max_distance_km: float) -> dict:
    """
    Vergleicht die Streckenlaenge der hochgeladenen GPX mit der bisherigen
    maximalen Laufdistanz (aus den Trainingsdaten).

    Rueckgabe: {
        "is_too_ambitious": bool,
        "threshold_km": float,       # ab welcher Distanz es "zu viel" waere
        "ratio": float,              # Strecke / bisherige Maximaldistanz
        "message": str,              # fertige Fehlermeldung, falls zu ambitioniert
    }
    """
    if max_distance_km <= 0:
        # Keine Trainingsdaten vorhanden - koennen wir nicht sinnvoll
        # bewerten, geben aber sicherheitshalber eine Warnung statt eines
        # falschen "alles ok".
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
