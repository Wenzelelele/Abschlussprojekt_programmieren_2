"""
training_tab.py
----------------
Streamlit-UI fuer den Trainingsdaten-Tab: Upload von GPX/FIT-Laeufen,
Auswahl der HF-Zonen-Methode, Anzeige der Effizienz je Gelaendeart und
Trainingsempfehlung. Schreibt die Ergebnisse in st.session_state
(Datenvertrag mit route_tab.py) und persistiert sie via TinyDB.
"""

import pandas as pd
import streamlit as st

from data.training_processing import (
    calc_terrain_split,
    load_training_fit,
    load_training_gpx,
    preprocess,
)
from functions.hr_zones import (
    estimate_max_hr_tanaka,
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


def _load_summary_into_session(username: str) -> None:
    """
    Befuellt session_state beim ersten Oeffnen aus der TinyDB, falls dort
    gespeicherte Aggregate liegen. Der Marker training_data_source
    verhindert, dass echte Daten spaeter von Mock-Werten (main.py)
    verdeckt werden - und dass wir bei jedem Rerun neu laden.
    """
    if st.session_state.get("training_data_source") is not None:
        return

    summary = load_training_summary(username)
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


def _zone_boundaries_from_ui(profile) -> dict:
    """
    Rendert die Auswahl der HF-Zonen-Methode und gibt die fertigen
    Grenzen zurueck. Default kommt aus dem Person-Profil (Feld
    zone_method, siehe Abstimmung mit Jannis) - solange das Feld dort
    noch nicht existiert, faellt die Auswahl auf 'max_hr' zurueck, weil
    max_hr in users.csv bereits fuer alle Nutzer gepflegt ist.
    """
    methods = list(ZONE_METHOD_LABELS)
    profile_method = None
    if profile is not None and "zone_method" in profile.index:
        profile_method = profile["zone_method"]

    default_index = methods.index(profile_method) if profile_method in methods else 0
    method = st.selectbox(
        "HF-Zonen-Methode",
        methods,
        index=default_index,
        format_func=ZONE_METHOD_LABELS.get,
        help="Wird kuenftig im Profil gespeichert (Abstimmung mit Jannis laeuft).",
    )

    profile_max_hr = float(profile["max_hr"]) if profile is not None else 190.0
    profile_age = int(profile["age"]) if profile is not None else 30

    if method == "max_hr":
        max_hr = st.number_input(
            "Maximale Herzfrequenz (bpm)", 120.0, 230.0, profile_max_hr
        )
        return get_zone_boundaries_maxhr(max_hr)

    if method == "age":
        age = st.number_input("Alter (Jahre)", 10, 100, profile_age)
        st.caption(
            f"Geschaetzte max. HF (Tanaka): {estimate_max_hr_tanaka(age):.0f} bpm"
        )
        return get_zone_boundaries_age(age)

    # manuell: 4 Trennwerte, Defaults als uebliche Prozentgrenzen der max_hr
    cols = st.columns(4)
    defaults = [0.6, 0.7, 0.8, 0.9]
    bounds = [
        col.number_input(
            f"Z{i+1}/Z{i+2} (bpm)", 60.0, 230.0, round(pct * profile_max_hr)
        )
        for i, (col, pct) in enumerate(zip(cols, defaults))
    ]
    return get_zone_boundaries_manual(bounds)


def _run_pipeline(uploaded_files, zone_boundaries: dict, username: str) -> TrainingData:
    """Volle Pipeline: Datei -> preprocess -> terrain -> TrainingData."""
    training = TrainingData(person_id=username)

    for i, file in enumerate(uploaded_files):
        loader = (
            load_training_fit
            if file.name.lower().endswith(".fit")
            else load_training_gpx
        )
        run_df = loader(file)
        run_df = preprocess(run_df, zone_boundaries)
        run_df = calc_terrain_split(run_df)
        run_df["run_id"] = f"{i}_{file.name}"
        training.add_run(run_df)

    training.compute_all()
    return training


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

    _load_summary_into_session(username)
    profile = get_user_data(username)

    st.markdown(
        "Lade einen vergangenen Lauf als **GPX + FIT** hoch. Daraus berechnen "
        "wir deine Effizienz je Gelaendeart - die Basis fuer die "
        "Pace-Vorhersage im Routen-Tab."
    )

    zone_boundaries = _zone_boundaries_from_ui(profile)
    uploaded_files = st.file_uploader(
        "Trainingslauf hochladen (GPX und/oder FIT)",
        type=["gpx", "fit"],
        accept_multiple_files=True,
    )

    if uploaded_files and st.button("Trainingsdaten auswerten", type="primary"):
        try:
            with st.spinner("Werte Laeufe aus..."):
                training = _run_pipeline(uploaded_files, zone_boundaries, username)
        except ValueError as exc:
            st.error(f"Auswertung fehlgeschlagen: {exc}")
            return

        if not training.ef_factors:
            st.error(
                "Keine verwertbaren Datenpunkte gefunden (fehlt die Herzfrequenz in der Datei?)."
            )
            return

        save_training_summary(
            username,
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
        # Gepoolter df nur fuer die Detail-Anzeige in DIESER Session -
        # persistiert werden bewusst nur die Aggregate.
        st.session_state["training_df"] = training.df
        st.session_state["training_ef_factors"] = training.ef_factors
        st.success(f"{len(uploaded_files)} Lauf/Laeufe ausgewertet und gespeichert.")

    _render_results()


def _render_results() -> None:
    """Zeigt die aktuellen Ergebnisse aus session_state (falls vorhanden)."""
    if st.session_state.get("training_data_source") is None:
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
