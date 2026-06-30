"""
route_tab.py
------------
Der Streckenplanung-Tab: GPX-Upload, direkt darunter Karte+Slider,
und zwei synchronisierte Auswahlboxen (HF-Zone / Zielzeit) darüber.

PRINZIP DER ZONE<->ZEIT SYNCHRONISIERUNG:
Beide Eingabefelder sind gleichzeitig sichtbar. Über st.session_state
merken wir uns, welches Feld zuletzt vom Nutzer geändert wurde
("last_changed" = "zone" oder "time"). Beim Neu-Rendern der Seite
rechnen wir dann NUR in die jeweils nötige Richtung:
  - zuletzt Zone geändert -> Zone bestimmt die Zeit (Zone -> Zeit)
  - zuletzt Zeit geändert  -> Zeit bestimmt die Zone (Zeit -> Zone)
So entsteht kein Konflikt und keine Rechen-Schleife.

ERWARTETE EINGABE (von eurem "data"-Baustein, in st.session_state):
    st.session_state["pace_hr_bins"] = {
        "up":   {"Z1": ..., "Z2": ..., "Z3": ..., "Z4": ..., "Z5": ...},
        "flat": {"Z1": ..., ...},
        "down": {"Z1": ..., ...},
    }
    st.session_state["ef_up"] = float
    st.session_state["ef_flat"] = float
    st.session_state["ef_down"] = float
    st.session_state["max_distance_km"] = float
"""


import streamlit as st
import pydeck as pdk
import pandas as pd

from data.gpx_processing import parse_gpx, resample_route
from functions.pace_model import (
    HR_ZONES,
    compute_ef_factors,
    estimate_segments_for_zone,
    estimate_zone_for_target_time,
    total_time_for_zone,
)
from functions.distance_check import check_distance_ambition


HR_ZONE_LABELS = {
    "Z1": "Z1 – Locker",
    "Z2": "Z2 – Grundlage",
    "Z3": "Z3 – Moderat",
    "Z4": "Z4 – Schwelle",
    "Z5": "Z5 – Hart",
}


def _check_prerequisites() -> bool:
    """Prüft, ob die benötigten Daten aus dem 'data'-Baustein vorliegen."""
    required_keys = ["pace_hr_bins", "ef_up", "ef_flat", "ef_down", "max_distance_km"]
    missing = [k for k in required_keys if k not in st.session_state]

    if missing:
        st.info(
            "**Bitte erst Trainingsdaten hochladen.**\n\n"
            f"Für diesen Tab fehlen noch folgende Werte: {', '.join(missing)}. "
            "Diese werden im Trainingsdaten-Tab berechnet."
        )
        return False
    return True


def _format_pace(sec_per_km) -> str:
    if sec_per_km is None:
        return "–"
    m = int(sec_per_km // 60)
    s = int(round(sec_per_km % 60))
    if s == 60:
        m += 1
        s = 0
    return f"{m}:{s:02d} /km"


def _format_time(total_sec: float) -> str:
    total_sec = int(round(total_sec))
    h = total_sec // 3600
    m = (total_sec % 3600) // 60
    s = total_sec % 60
    if h > 0:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"


# ---------------------------------------------------------------------
# Callbacks fuer die Zone<->Zeit Synchronisierung
# ---------------------------------------------------------------------

def _on_zone_change():
    st.session_state["last_changed"] = "zone"


def _on_time_change():
    st.session_state["last_changed"] = "time"


def render_route_tab():
    st.subheader("Streckenplanung")

    if not _check_prerequisites():
        return

    pace_hr_bins = st.session_state["pace_hr_bins"]
    ef_factors = compute_ef_factors(
        st.session_state["ef_up"],
        st.session_state["ef_flat"],
        st.session_state["ef_down"],
    )
    max_distance_km = st.session_state["max_distance_km"]

    # -------------------------------------------------------------
    # Schritt A: GPX-Upload - der EINZIGE Button vor dem Ergebnis
    # -------------------------------------------------------------
    uploaded_gpx = st.file_uploader("GPX-Datei der Strecke hochladen", type=["gpx"])

    if uploaded_gpx is None:
        st.caption("Lade eine GPX-Datei hoch, um die Streckenplanung zu starten.")
        return

    try:
        route = parse_gpx(uploaded_gpx)
    except Exception as e:
        st.error(f"Konnte GPX-Datei nicht lesen: {e}")
        return

    segments = resample_route(route, segment_length_m=100.0)
    route_distance_km = route.total_distance_m / 1000.0

    # -------------------------------------------------------------
    # Schritt B: Streckenlaengen-Check (unabhaengig von Zone/Zeit)
    # -------------------------------------------------------------
    distance_check = check_distance_ambition(route_distance_km, max_distance_km)
    if distance_check["is_too_ambitious"]:
        st.error(distance_check["message"])
        return

    st.markdown(
        f"**{route.name}** · {route_distance_km:.2f} km · "
        f"⬆ {route.total_ascent_m:.0f} m · ⬇ {route.total_descent_m:.0f} m"
    )

    # -------------------------------------------------------------
    # Schritt C: Zone <-> Zeit Synchronisierung
    # -------------------------------------------------------------
    if "last_changed" not in st.session_state:
        st.session_state["last_changed"] = "zone"
    if "selected_zone" not in st.session_state:
        st.session_state["selected_zone"] = "Z3"
    if "selected_minutes" not in st.session_state:
        st.session_state["selected_minutes"] = 30
    if "selected_seconds" not in st.session_state:
        st.session_state["selected_seconds"] = 0

    error_message = None

    # Zuerst auf Basis von "last_changed" die fehlende Seite berechnen,
    # BEVOR die Widgets gezeichnet werden - so zeigen die Widgets sofort
    # den aktuellen, synchronisierten Wert.
    if st.session_state["last_changed"] == "zone":
        zone = st.session_state["selected_zone"]
        seg_with_pace = estimate_segments_for_zone(segments, zone, pace_hr_bins, ef_factors)
        total_sec = total_time_for_zone(seg_with_pace)

        st.session_state["selected_minutes"] = int(total_sec // 60)
        st.session_state["selected_seconds"] = int(round(total_sec % 60))

        result_segments = seg_with_pace
        chosen_zone = zone

    else:  # last_changed == "time"
        target_sec = (
            st.session_state["selected_minutes"] * 60 + st.session_state["selected_seconds"]
        )
        result = estimate_zone_for_target_time(segments, target_sec, pace_hr_bins, ef_factors)

        if result["is_too_ambitious"]:
            error_message = result["ambition_message"]
            result_segments = None
            chosen_zone = None
        else:
            st.session_state["selected_zone"] = result["chosen_zone"]
            result_segments = result["segments"]
            chosen_zone = result["chosen_zone"]

    # -------------------------------------------------------------
    # Schritt D: die zwei Auswahlboxen (UEBER der Karte, wie gefordert)
    # -------------------------------------------------------------
    col1, col2 = st.columns(2)

    with col1:
        st.write("Ziel-HF-Zone")
        st.selectbox(
            " ",
            options=HR_ZONES,
            format_func=lambda z: HR_ZONE_LABELS.get(z, z),
            key="selected_zone",
            on_change=_on_zone_change,
        )

    with col2:
        st.write("Zielzeit")
        tc1, tc2 = st.columns(2)
        tc1.number_input(
            "Minuten", min_value=0, max_value=600, step=1,
            key="selected_minutes", on_change=_on_time_change,
        )
        tc2.number_input(
            "Sekunden", min_value=0, max_value=59, step=1,
            key="selected_seconds", on_change=_on_time_change,
        )

    # -------------------------------------------------------------
    # Schritt E: Fehleranzeige bei zu ambitionierter Zielzeit
    # -------------------------------------------------------------
    if error_message:
        st.error(error_message)
        return

    if result_segments is None or result_segments.empty:
        st.warning("Keine ausreichenden Trainingsdaten für eine Schätzung vorhanden.")
        return

    total_sec_final = total_time_for_zone(result_segments)
    st.success(
        f"**{HR_ZONE_LABELS.get(chosen_zone, chosen_zone)}** → Gesamtzeit ca. "
        f"**{_format_time(total_sec_final)}**"
    )

    # -------------------------------------------------------------
    # Schritt F: Karte + Slider mit bewegtem Punkt
    # -------------------------------------------------------------
    _render_map_with_slider(result_segments)


def _render_map_with_slider(segments):
    """Karte mit farbcodierter Pace-Linie + Slider, der einen Punkt entlang
    der Strecke bewegt. Direkt unter dem GPX-Upload sichtbar"""
  

    p_min = segments["pace_sec_per_km"].min()
    p_max = segments["pace_sec_per_km"].max()

    def pace_to_color(pace):
        if pd.isna(pace) or p_max == p_min:
            return [255, 184, 28]
        t = (pace - p_min) / (p_max - p_min)
        t = max(0.0, min(1.0, t))
        fast, mid, slow = [0, 168, 107], [255, 184, 28], [220, 50, 50]
        if t < 0.5:
            t2 = t / 0.5
            return [int(a + (b - a) * t2) for a, b in zip(fast, mid)]
        t2 = (t - 0.5) / 0.5
        return [int(a + (b - a) * t2) for a, b in zip(mid, slow)]

    path_data = []
    for i in range(len(segments) - 1):
        row_a = segments.iloc[i]
        row_b = segments.iloc[i + 1]
        path_data.append({
            "path": [[row_a["lon"], row_a["lat"]], [row_b["lon"], row_b["lat"]]],
            "color": pace_to_color(row_a["pace_sec_per_km"]),
        })

    path_layer = pdk.Layer(
        "PathLayer", data=path_data, get_path="path", get_color="color",
        width_min_pixels=5, pickable=False,
    )

    marker_idx = st.slider("Streckenabschnitt", 0, len(segments) - 1, 0)
    marker_row = segments.iloc[marker_idx]

    marker_layer = pdk.Layer(
        "ScatterplotLayer",
        data=[{"lat": marker_row["lat"], "lon": marker_row["lon"]}],
        get_position=["lon", "lat"], get_fill_color=[30, 30, 220],
        get_radius=35, radius_min_pixels=9, radius_max_pixels=22,
    )

    view_state = pdk.ViewState(
        latitude=segments["lat"].mean(), longitude=segments["lon"].mean(),
        zoom=13, pitch=0,
    )
    deck = pdk.Deck(
        layers=[path_layer, marker_layer], initial_view_state=view_state,
        map_provider="carto", map_style="light",
    )
    st.pydeck_chart(deck, use_container_width=True)

    mc1, mc2, mc3 = st.columns(3)
    mc1.metric("Position", f"{marker_row['mid_m']/1000:.2f} km")
    mc2.metric("Steigung", f"{marker_row['grade_pct']:+.1f} %")
    mc3.metric("Ziel-Pace", _format_pace(marker_row["pace_sec_per_km"]))
