"""
training_tab.py
----------------
Streamlit-UI fuer den Trainingsdaten-Tab: Upload von GPX/FIT-Laeufen,
Auswahl der HF-Zonen-Methode, Anzeige der Effizienz je Gelaendeart und
Trainingsempfehlung. Schreibt die Ergebnisse in st.session_state
(Datenvertrag mit route_tab.py) und persistiert sie via TinyDB.
"""

import math

import pandas as pd
import streamlit as st

from data.training_processing import (
    calc_terrain_split,
    load_training_fit,
    load_training_gpx,
    load_training_tcx,
    preprocess,
)
from functions.hr_zones import (
    get_zone_boundaries_age,
    get_zone_boundaries_manual,
    get_zone_boundaries_maxhr,
)
from functions.training_data import TrainingData
from functions.training_storage import load_training_summary, save_training_summary
from functions.user_profil import get_user_data

TERRAIN_LABELS_DE = {"up": "Bergauf", "flat": "Flach", "down": "Bergab"}

ZONE_METHOD_LABELS = {
    "max_hr": "Prozent der maximalen HF",
    "age": "Altersbasiert (Tanaka-Formel)",
    "manual": "Manuelle Zonengrenzen",
}

RECOMMENDATIONS = {
    "up": (
        "Deine Effizienz bergauf ist relativ zu deinen anderen Gelaendearten "
        "am schwaechsten. Baue 1x pro Woche Huegelintervalle ein "
        "(z.B. 8x 60 Sekunden zuegig bergauf, Trabpause bergab) und achte "
        "auf kurze Schritte und aufrechte Haltung am Anstieg."
    ),
    "flat": (
        "Deine Effizienz in der Ebene ist relativ zu deinen anderen "
        "Gelaendearten am schwaechsten. Klassische Tempodauerlaeufe "
        "(20-30 Minuten an der Schwelle) und Lauf-ABC fuer die "
        "Schrittoekonomie bringen hier am meisten."
    ),
    "down": (
        "Deine Effizienz bergab ist relativ zu deinen anderen Gelaendearten "
        "am schwaechsten. Trainiere kontrollierte Bergab-Laeufe auf leichtem "
        "Gefaelle (Schrittfrequenz hoch, Bremsen vermeiden) - die exzentrische "
        "Belastung braucht Gewoehnung, also dosiert steigern."
    ),
}


def _format_pace(sec_per_km: float) -> str:
    """Formatiert eine Pace in sec/km als 'M:SS min/km'."""
    minutes, seconds = divmod(int(round(sec_per_km)), 60)
    return f"{minutes}:{seconds:02d} min/km"


def display_terrain(df: pd.DataFrame | None, ef_factors: dict) -> None:
    """
    Zeigt die Effizienz je Gelaendeart als Balkendiagramm und (falls der
    gepoolte DataFrame in dieser Session vorliegt) eine Detail-Tabelle.

    Input:  df - terrain-klassifizierter DataFrame oder None (None nach
                 einem Login, wenn nur die gespeicherten Aggregate da sind)
            ef_factors - {"up": .., "flat": .., "down": ..}
    Output: None (rendert Streamlit-Elemente)
    """
    if not ef_factors:
        st.info("Noch keine Effizienzwerte vorhanden.")
        return

    chart_df = pd.DataFrame(
        {
            "Effizienzfaktor": [
                ef_factors[t] for t in ("up", "flat", "down") if t in ef_factors
            ]
        },
        index=[TERRAIN_LABELS_DE[t] for t in ("up", "flat", "down") if t in ef_factors],
    )
    st.markdown(
        "**Effizienzfaktor je Gelaendeart** (GAP-Tempo in m/min pro Puls-Schlag - hoeher = besser)"
    )
    st.bar_chart(chart_df, horizontal=True)

    if df is None or df.empty:
        return

    total_dist = df["dist_delta_m"].sum()
    rows = []
    for terrain, group in df.groupby("terrain"):
        rows.append(
            {
                "Gelaende": TERRAIN_LABELS_DE.get(terrain, terrain),
                "Anteil Distanz": f"{group['dist_delta_m'].sum() / total_dist * 100:.0f} %",
                "Ø Herzfrequenz": f"{group['hr'].mean():.0f} bpm",
                "Ø GAP-Pace": _format_pace(group["gap_pace"].mean()),
            }
        )
    st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")


def generate_recommendation(ef_factors: dict) -> str:
    """
    Formuliert einen Trainingstipp basierend auf der schwaechsten
    Gelaendeart (kleinster EF im Vergleich zum eigenen Durchschnitt).

    Input:  ef_factors - {"up": .., "flat": .., "down": ..}
    Output: Trainingsempfehlung als Text
    """
    if not ef_factors:
        return "Noch keine Trainingsdaten vorhanden - lade zuerst einen Lauf hoch."
    if len(ef_factors) < 2:
        return (
            "Deine bisherigen Laeufe enthalten nur eine Gelaendeart - fuer einen "
            "Vergleich (und einen gezielten Tipp) brauchst du Laeufe mit Anstiegen "
            "UND Flachstuecken."
        )

    weakest = min(ef_factors, key=ef_factors.get)
    avg_ef = sum(ef_factors.values()) / len(ef_factors)
    deficit_pct = (1 - ef_factors[weakest] / avg_ef) * 100

    return (
        f"{RECOMMENDATIONS[weakest]} "
        f"(Aktuell liegt dein Wert dort {deficit_pct:.0f} % unter deinem "
        f"eigenen Durchschnitt.)"
    )


# ---------------------------------------------------------------------
# Interne Bausteine des Tabs
# ---------------------------------------------------------------------


def _load_summary_into_session(person_id: str) -> None:
    """
    Befuellt session_state beim ersten Oeffnen aus der TinyDB, falls dort
    gespeicherte Aggregate liegen. Der Marker training_data_source
    verhindert unnoetiges Neuladen bei jedem Rerun. "mock" (Platzhalter
    aus main.py, falls der Route-Tab zuerst besucht wurde) zaehlt dabei
    NICHT als echte Datenquelle - echte gespeicherte Werte ueberschreiben
    den Mock.
    """
    if st.session_state.get("training_data_source") not in (None, "mock"):
        return

    summary = load_training_summary(person_id)
    if summary is None:
        return

    _write_contract_to_session(
        summary["ef_factors"],
        summary["pace_hr_bins"],
        summary["max_distance_km"],
        summary["max_elevation_m"],
        source="db",
    )


def _write_contract_to_session(
    ef_factors: dict,
    pace_hr_bins: dict,
    max_distance_km: float,
    max_elevation_m: float,
    source: str,
) -> None:
    """
    Schreibt den Datenvertrag fuer die anderen Tabs in st.session_state.
    Fehlt eine Gelaendeart komplett (z.B. nur Flach-Laeufe hochgeladen),
    wird ihr EF neutral mit dem Mittel der vorhandenen EFs aufgefuellt -
    compute_ef_factors in pace_model.py macht daraus dann Faktor ~1.0.
    """
    fallback_ef = sum(ef_factors.values()) / len(ef_factors) if ef_factors else 1.0

    st.session_state["pace_hr_bins"] = pace_hr_bins
    st.session_state["ef_up"] = ef_factors.get("up", fallback_ef)
    st.session_state["ef_flat"] = ef_factors.get("flat", fallback_ef)
    st.session_state["ef_down"] = ef_factors.get("down", fallback_ef)
    st.session_state["max_distance_km"] = max_distance_km
    st.session_state["max_elevation_m"] = max_elevation_m
    st.session_state["training_data_source"] = source


def _zone_boundaries_from_profile(profile) -> dict:
    """
    Baut die HF-Zonen-Grenzen ausschliesslich aus dem Person-Profil.
    Keine eigene Auswahl mehr im Trainings-Tab - zone_method/hr_bound_1-4
    werden im Profil-Tab gepflegt (Jannis), das Profil ist die einzige
    Quelle der Wahrheit dafuer. Fallback auf 'max_hr', falls das Profil
    (noch) keine zone_method hat - passt zum Default in user_profil.py.
    """
    method = "max_hr"
    if (
        profile is not None
        and "zone_method" in profile.index
        and pd.notna(profile["zone_method"])
    ):
        method = profile["zone_method"]

    max_hr = (
        float(profile["max_hr"])
        if profile is not None and "max_hr" in profile.index
        else 190.0
    )

    if method == "manual":
        bounds = [profile.get(f"hr_bound_{i}") for i in range(1, 5)]
        if any(pd.isna(b) for b in bounds):
            st.warning(
                "Im Profil ist die manuelle HF-Zonen-Methode gewaehlt, aber "
                "nicht alle 4 Grenzwerte sind ausgefuellt - nutze stattdessen "
                "die prozentuale Berechnung ueber deine max. HF. Trag die "
                "fehlenden Werte im Profil-Tab nach."
            )
            return get_zone_boundaries_maxhr(max_hr)
        return get_zone_boundaries_manual([float(b) for b in bounds])

    if method == "age" and profile is not None and "age" in profile.index:
        return get_zone_boundaries_age(int(profile["age"]))

    return get_zone_boundaries_maxhr(max_hr)


MAX_MANUAL_RUNS = 30


def _run_pipeline(
    uploaded_files, zone_boundaries: dict, person_id: str
) -> tuple[TrainingData, list[tuple[str, str]]]:
    """
    Volle Pipeline fuer den manuellen Multi-Datei-Upload:
    Datei -> preprocess -> terrain -> TrainingData.

    Zwei-Phasen-Ansatz wegen MAX_MANUAL_RUNS: Phase 1 laedt ALLE Dateien nur
    (billig, kein Rolling-Window/Haversine), um ihr Startdatum zu kennen.
    Phase 2 sortiert nach Datum und schickt nur die neuesten MAX_MANUAL_RUNS
    davon durch preprocess() - das ist der teure Teil (iterative haversine_m
    aus gpx_processing.py). Aeltere Ueberschuss-Dateien werden uebersprungen,
    nicht verworfen ohne Erklaerung.

    Eine einzelne nicht auswertbare Datei (Ladefehler oder z.B. fehlende
    Herzfrequenz) bricht nie den ganzen Batch ab - siehe breiter except-Block.

    Output: (TrainingData, skipped) - skipped: Liste aus (dateiname, grund)
    """
    training = TrainingData(person_id=person_id)
    skipped: list[tuple[str, str]] = []
    loaded: list[tuple[object, pd.DataFrame]] = []

    for file in uploaded_files:
        try:
            suffix = file.name.lower().rsplit(".", 1)[-1]
            loader = {"fit": load_training_fit, "tcx": load_training_tcx}.get(
                suffix, load_training_gpx
            )
            raw_df = loader(file)
            loaded.append((file, raw_df))
        except Exception as exc:  # noqa: BLE001 - siehe Docstring
            skipped.append((file.name, str(exc)))

    # Neueste zuerst - Startzeitpunkt eines Laufs ist das Minimum der time-Spalte
    loaded.sort(key=lambda pair: pair[1]["time"].min(), reverse=True)

    to_process = loaded[:MAX_MANUAL_RUNS]
    for file, _ in loaded[MAX_MANUAL_RUNS:]:
        skipped.append(
            (
                file.name,
                f"Nicht verarbeitet - beim manuellen Upload werden nur die "
                f"neuesten {MAX_MANUAL_RUNS} Laeufe ausgewertet.",
            )
        )

    for i, (file, raw_df) in enumerate(to_process):
        try:
            run_df = preprocess(raw_df, zone_boundaries)
            run_df = calc_terrain_split(run_df)
            run_df["run_id"] = f"{i}_{file.name}"
            training.add_run(run_df)
        except Exception as exc:  # noqa: BLE001
            skipped.append((file.name, str(exc)))

    training.compute_all()
    return training, skipped


def render_training_tab() -> None:
    """
    Einstiegspunkt fuer den Tab (Namenskonvention wie render_route_tab):
    laedt gespeicherte Aggregate, nimmt neue GPX/FIT-Uploads entgegen,
    rechnet die Pipeline und aktualisiert session_state + TinyDB.
    """
    st.header("Trainingsdaten")
    username = st.session_state.get("current_user")
    if not username:
        st.warning("Bitte zuerst einloggen.")
        return

    profile = get_user_data(username)
    # Stabile user_id aus dem Profil (Jannis) als Speicher-Schluessel -
    # Fallback auf den username, falls die ID (noch) fehlt.
    person_id = username
    if (
        profile is not None
        and "user_id" in profile.index
        and pd.notna(profile["user_id"])
    ):
        person_id = str(profile["user_id"])

    _load_summary_into_session(person_id)

    st.markdown(
        "Lade vergangene Laeufe hoch (FIT, TCX oder GPX). Daraus berechnen "
        "wir deine Effizienz je Gelaendeart - die Basis fuer die "
        "Pace-Vorhersage im Routen-Tab."
    )

    zone_boundaries = _zone_boundaries_from_profile(profile)
    method_label = ZONE_METHOD_LABELS.get(
        (
            profile["zone_method"]
            if profile is not None and "zone_method" in profile.index
            else "max_hr"
        ),
        "Prozent der maximalen HF",
    )
    st.caption(
        f"HF-Zonen-Methode: **{method_label}** (aus deinem Profil). Falls du "
        "das aendern willst - Berechnungsmethode, max. HF, Alter oder "
        "manuelle Zonengrenzen - trag das im **Profil-Tab** ein, bevor du "
        "hier hochlaedst."
    )
    uploaded_files = st.file_uploader(
        "Trainingslaeufe hochladen (FIT, TCX oder GPX)",
        type=["gpx", "fit", "tcx"],
        accept_multiple_files=True,
        help=(
            "Exportiere einzelne Laeufe direkt aus deiner Sport-App "
            "(z.B. Garmin Connect oder Wahoo: Aktivitaet oeffnen -> "
            "Exportieren -> FIT oder TCX) und lade am besten ein paar "
            "lange Laeufe oder Rennen hoch. Bei mehr als "
            f"{MAX_MANUAL_RUNS} Dateien werden nur die neuesten "
            f"{MAX_MANUAL_RUNS} ausgewertet."
        ),
    )

    if uploaded_files and st.button("Trainingsdaten auswerten", type="primary"):
        with st.spinner("Werte Laeufe aus..."):
            training, skipped = _run_pipeline(
                uploaded_files, zone_boundaries, person_id
            )

        if skipped:
            with st.expander(
                f"{len(skipped)} von {len(uploaded_files)} Datei(en) uebersprungen",
                expanded=not training.ef_factors,
            ):
                for name, reason in skipped:
                    st.warning(f"**{name}:** {reason}")

        if not training.ef_factors:
            st.error(
                "Keine der hochgeladenen Dateien konnte ausgewertet werden "
                "(Details oben)."
            )
            return

        save_training_summary(
            person_id,
            training.ef_factors,
            training.pace_hr_bins,
            training.max_distance_km,
            training.max_elevation_m,
        )
        _write_contract_to_session(
            training.ef_factors,
            training.pace_hr_bins,
            training.max_distance_km,
            training.max_elevation_m,
            source="upload",
        )
        # Gepoolter df + Zonen-Grenzen nur fuer die Detail-Anzeige in DIESER
        # Session - persistiert werden bewusst nur die Aggregate.
        st.session_state["training_df"] = training.df
        st.session_state["training_ef_factors"] = training.ef_factors
        st.session_state["hr_zone_boundaries"] = zone_boundaries
        n_ok = len(uploaded_files) - len(skipped)
        st.success(
            f"{n_ok} von {len(uploaded_files)} Lauf/Laeufen ausgewertet und gespeichert."
        )

    _render_results()


def _render_results() -> None:
    """Zeigt die aktuellen Ergebnisse aus session_state (falls vorhanden).
    Der Mock aus main.py ("mock") zaehlt nicht als echte Daten - der Tab
    zeigt dann denselben Hinweis wie bei komplett fehlenden Daten."""
    if st.session_state.get("training_data_source") in (None, "mock"):
        st.info(
            "Noch keine Trainingsdaten vorhanden. Lade oben einen Lauf hoch, "
            "um deine HF-Zonen, Effizienzwerte und eine Trainingsempfehlung "
            "zu sehen."
        )
        return

    ef_factors = st.session_state.get(
        "training_ef_factors",
        {
            "up": st.session_state["ef_up"],
            "flat": st.session_state["ef_flat"],
            "down": st.session_state["ef_down"],
        },
    )

    st.divider()
    col1, col2 = st.columns(2)
    col1.metric("Laengster Lauf", f"{st.session_state['max_distance_km']:.1f} km")
    col2.metric("Meiste Hoehenmeter", f"{st.session_state['max_elevation_m']:.0f} m")

    if "hr_zone_boundaries" in st.session_state:
        with st.expander("Deine HF-Zonen-Grenzen"):
            bounds = st.session_state["hr_zone_boundaries"]
            st.table(
                pd.DataFrame(
                    {
                        "Zone": list(bounds.keys()),
                        "Von (bpm)": [f"{lo:.0f}" for lo, _ in bounds.values()],
                        "Bis (bpm)": [
                            "∞" if hi == math.inf else f"{hi:.0f}"
                            for _, hi in bounds.values()
                        ],
                    }
                )
            )

    display_terrain(st.session_state.get("training_df"), ef_factors)
    st.info(generate_recommendation(ef_factors))

    with st.expander(
        "Basis-Pace je Gelaende und HF-Zone (Grundlage der Routen-Vorhersage)"
    ):
        bins = st.session_state["pace_hr_bins"]
        table = pd.DataFrame(
            {
                TERRAIN_LABELS_DE[t]: {
                    zone: _format_pace(p) for zone, p in zones.items()
                }
                for t, zones in bins.items()
            }
        )
        st.dataframe(table.sort_index(), width="stretch")
