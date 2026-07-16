"""
route_tab.py
------------
Streckenplanung-Tab: Kopfbereich mit Routeninfo + Farb-Legende, darunter
vier Spalten (Eingabe-Panel, Karte, Höhenprofil, Pace-Metriken/Export),
unten die Zone/Zeit-Prognose - alles ohne Scrollen auf einen Blick.

ZONE<->ZEIT SYNC: st.session_state merkt sich, welches Feld zuletzt
geändert wurde ("last_changed"), und rechnet beim Rerun nur in die
jeweils andere Richtung - kein Konflikt, keine Rechen-Schleife.

Erwartet in st.session_state (vom Trainingsdaten-Tab):
    pace_hr_bins = {"up": {"Z1": ..., ...}, "flat": {...}, "down": {...}}
    ef_up, ef_flat, ef_down, max_distance_km = float
"""


import io

import streamlit as st
import pydeck as pdk
import pandas as pd
import plotly.graph_objects as go

from data.gpx_processing import parse_gpx, resample_route
from functions.fit_export import build_fit_workout
from functions.pace_model import (
    HR_ZONES,
    compute_ef_factors,
    estimate_segments_for_zone,
    estimate_zone_for_target_time,
    total_time_for_zone,
)
from functions.distance_check import check_distance_ambition
from functions.route_storage import delete_route, get_routes_for_user, save_route

# Mitgelieferte Beispielstrecke, damit der Tab sofort getestet werden kann,
# ohne dass man eine eigene GPX-Datei zur Hand haben muss.
SAMPLE_GPX_PATH = "data/sample_route.gpx"
SAMPLE_ROUTE_LABEL = "Beispielstrecke (Testdaten)"


def _load_sample_gpx_text() -> str:
    with open(SAMPLE_GPX_PATH, encoding="utf-8") as f:
        return f.read()


def _route_label(route: dict) -> str:
    """Einheitliche Beschriftung einer gespeicherten Route fuer die Auswahlbox."""
    return f"{route['route_name']} · {route['distance_km']} km · {route['uploaded_at'][:16]}"


HR_ZONE_LABELS = {
    "Z1": "Z1 – Locker",
    "Z2": "Z2 – Grundlage",
    "Z3": "Z3 – Moderat",
    "Z4": "Z4 – Schwelle",
    "Z5": "Z5 – Hart",
}


def _render_data_source_notice() -> None:
    """Hinweis, falls noch mit Mock- statt echten Trainingsdaten gerechnet
    wird (main.py setzt training_data_source). Blockiert nichts."""
    if st.session_state.get("training_data_source") == "mock":
        st.info(
            "**Es werden Mock-Testdaten verwendet.** Für eine echte Prognose "
            "lade zuerst im Trainingsdaten-Tab einen Lauf hoch."
        )


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
# Callbacks für die Zone<->Zeit Synchronisierung
# ---------------------------------------------------------------------

def _on_zone_change():
    st.session_state["last_changed"] = "zone"


def _on_time_change():
    st.session_state["last_changed"] = "time"

def _pace_to_color(pace, p_min, p_max):
    """
    Wandelt eine Pace (sec/km) in eine RGB-Farbe um: rot (schnell) ->
    gelb (mittel) -> grün (langsam). Wird sowohl von der Karte als auch
    vom Höhenprofil genutzt, damit beide Visualisierungen exakt dieselbe
    Farblogik verwenden.
    """


    if pd.isna(pace) or p_max == p_min:
        return [255, 184, 28]
    t = (pace - p_min) / (p_max - p_min)
    t = max(0.0, min(1.0, t))
    fast, mid, slow = [220, 50, 50], [255, 184, 28], [0, 168, 107]
    if t < 0.5:
        t2 = t / 0.5
        return [int(a + (b - a) * t2) for a, b in zip(fast, mid)]
    t2 = (t - 0.5) / 0.5
    return [int(a + (b - a) * t2) for a, b in zip(mid, slow)]


def _render_pace_legend():
    """Zeigt einen Farbverlauf-Balken, der die Pace-Einfärbung von Karte
    und Höhenprofil erklärt (rot = schnell, grün = langsam)."""
    fast_r, fast_g, fast_b = 220, 50, 50
    mid_r, mid_g, mid_b = 255, 184, 28
    slow_r, slow_g, slow_b = 0, 168, 107

    st.markdown(
        f"""
        <div style="margin: 0.25rem 0 1rem 0;">
            <div style="
                height: 12px;
                border-radius: 6px;
                background: linear-gradient(
                    to right,
                    rgb({fast_r},{fast_g},{fast_b}),
                    rgb({mid_r},{mid_g},{mid_b}),
                    rgb({slow_r},{slow_g},{slow_b})
                );
            "></div>
            <div style="display: flex; justify-content: space-between; font-size: 0.8rem;">
                <span>Schnell</span>
                <span>Langsam</span>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_route_tab():
    st.subheader("Streckenplanung")
    _render_data_source_notice()

    pace_hr_bins = st.session_state["pace_hr_bins"]
    ef_factors = compute_ef_factors(
        st.session_state["ef_up"],
        st.session_state["ef_flat"],
        st.session_state["ef_down"],
    )
    max_distance_km = st.session_state["max_distance_km"]

    # Layout-Slots vorab anlegen (bestimmt Position auf der Seite),
    # befuellt wird erst weiter unten im Code.
    header = st.container()
    control_col, map_col, profile_col, side_col = st.columns([1.6, 2, 2, 1])
    footer = st.container()

    with control_col:
        st.markdown("**Einstellungen**")
        control_panel = st.container(border=True)

    # -------------------------------------------------------------
    # Schritt A: gespeicherte Route wählen ODER neue GPX hochladen
    # -------------------------------------------------------------
    with control_panel:
    

        username = st.session_state.current_user
        saved_routes = get_routes_for_user(username)

        # Beispielstrecke immer als erste Option, "Neue Route hochladen" immer letzte
        route_options = (
            [SAMPLE_ROUTE_LABEL]
            + [_route_label(r) for r in saved_routes]
            + ["Neue Route hochladen"]
        )
        chosen_option = st.selectbox("Route", route_options, key="route_choice")

        gpx_source = None

        if chosen_option == SAMPLE_ROUTE_LABEL:
            gpx_source = io.StringIO(_load_sample_gpx_text())

        elif chosen_option == "Neue Route hochladen":
            uploaded_gpx = st.file_uploader("GPX-Datei der Strecke hochladen", type=["gpx"])

            if uploaded_gpx is None:
                st.caption("Lade eine GPX-Datei hoch, um die Streckenplanung zu starten.")
                return

            gpx_text = uploaded_gpx.getvalue().decode("utf-8")
            saved_route = save_route(username, uploaded_gpx.name, gpx_text)
            gpx_source = io.StringIO(gpx_text)

            # sonst faellt die Auswahlbox beim naechsten Rerun auf die
            # Beispielstrecke zurueck, weil sich route_options aendert
            st.session_state["route_choice"] = _route_label(saved_route)

        else:
            chosen_route = saved_routes[route_options.index(chosen_option) - 1]
            gpx_source = io.StringIO(chosen_route["gpx_content"])

            if st.button("Route löschen"):
                delete_route(chosen_route.doc_id)
                st.rerun()

    try:
        route = parse_gpx(gpx_source)
    except Exception as e:
        with header:
            st.error(f"Konnte GPX-Datei nicht lesen: {e}")
        return

    segments = resample_route(route, segment_length_m=100.0)
    route_distance_km = route.total_distance_m / 1000.0

    # Slider braucht nur die Segment-Anzahl, kann also schon hier stehen
    with control_panel:
        #st.caption("Position auf der Strecke")
        marker_idx = st.slider("Position auf der Strecke", 0, len(segments) - 1, 0)

    # -------------------------------------------------------------
    # Schritt B: Streckenlängen-Check (unabhängig von Zone/Zeit)
    # -------------------------------------------------------------
    distance_check = check_distance_ambition(route_distance_km, max_distance_km)
    if distance_check["is_too_ambitious"]:
        with header:
            st.info(distance_check["message"])

    with header:
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
        st.session_state["selected_zone"] = "Z2"
    if "selected_minutes" not in st.session_state:
        st.session_state["selected_minutes"] = 30
    if "selected_seconds" not in st.session_state:
        st.session_state["selected_seconds"] = 0

    error_message = None
    result_segments = None
    chosen_zone = None

    # fehlende Seite berechnen BEVOR die Widgets gezeichnet werden, damit
    # sie gleich den synchronisierten Wert zeigen
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

        result_segments = result["segments"]
        chosen_zone = result["chosen_zone"]
        # Auswahlbox auf die prognostizierte Zone nachziehen, spiegelbildlich
        # zum "zone"-Fall oben
        st.session_state["selected_zone"] = chosen_zone

    # -------------------------------------------------------------
    # Schritt D: die zwei synchronisierten Auswahlboxen (Panel)
    # -------------------------------------------------------------
    with control_panel:
        st.caption("Ziel")

        st.selectbox(
            "Ziel-HF-Zone",
            options=HR_ZONES,
            format_func=lambda z: HR_ZONE_LABELS.get(z, z),
            key="selected_zone",
            on_change=_on_zone_change,
        )

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
    # Schritt E: Legende oben, Prognose/Fehler kommen erst im footer -
    # die Gueltigkeitspruefung muss aber schon hier passieren
    # -------------------------------------------------------------
    with header:
        _render_pace_legend()

    if result_segments is None or result_segments.empty:
        with footer:
            st.warning("Keine ausreichenden Trainingsdaten für eine Schätzung vorhanden.")
        return

    marker_row = result_segments.iloc[marker_idx]

    # -------------------------------------------------------------
    # Schritt G: Karte, Höhenprofil und rechte Spalte mit Pace-Metriken
    # + Export, alle synchron zum selben Slider/marker_idx
    # -------------------------------------------------------------
    with map_col:
        st.markdown("**Strecke**")
        _render_map(result_segments, marker_idx)

    with profile_col:
        st.markdown("**Höhenprofil**")
        _render_elevation_profile(result_segments, marker_idx)

    with side_col:
        st.markdown("**Position**")

        side_panel = st.container(border=True)

        with side_panel:
            with st.container(key="route_pace_metrics"):
                st.html(
                    """
                    <style>
                    .st-key-route_pace_metrics [data-testid="stMetricValue"] { font-size: 1.3rem; }
                    .st-key-route_pace_metrics [data-testid="stMetricLabel"] { font-size: 0.8rem; }
                    </style>
                    """
                )
                st.metric("Distanz", f"{marker_row['mid_m']/1000:.2f} km")
                st.metric("Steigung", f"{marker_row['grade_pct']:+.1f} %")
                st.metric("Pace an Position", _format_pace(marker_row["pace_sec_per_km"]))

            st.divider()

            # -------------------------------------------------------
            # Schritt H: FIT-Workout-Export für Garmin Connect
            # -------------------------------------------------------
            workout_name_input = st.text_input(
                "Name des Workouts (max. 15 Zeichen)",
                value=route.name,
                max_chars=15,
            )

            fit_bytes = build_fit_workout(result_segments, workout_name=workout_name_input)
            st.download_button(
                "Herunterladen",
                icon="⬇️",
                data=fit_bytes,
                file_name=f"{workout_name_input.replace(' ', '_')}.fit",
                mime="application/octet-stream",
                use_container_width=True,
            )

    # -------------------------------------------------------------
    # Footer: Zone/Zeit-Prognose + ggf. Ambitioniert-Meldung, unter den
    # Grafiken (Slot wurde ganz oben vor den Spalten angelegt)
    # -------------------------------------------------------------
    with footer:
        with st.container(key="prognosis_card", border=True):
            st.html(
                """
                <style>
                .st-key-prognosis_card {
                    background-color: rgba(255, 244, 214, 0.96);
                }
                </style>
                """
            )
            total_sec_final = total_time_for_zone(result_segments)
            st.markdown(
                f"### 🏁 {HR_ZONE_LABELS.get(chosen_zone, chosen_zone)} · "
                f"Gesamtzeit ca. **{_format_time(total_sec_final)}**"
            )

            if error_message:
                st.error(error_message)

def _render_map(segments, marker_idx):
    """Karte mit farbcodierter Pace-Linie + Punkt an der Slider-Position."""
    import pydeck as pdk
 
    p_min = segments["pace_sec_per_km"].min()
    p_max = segments["pace_sec_per_km"].max()
 
    path_data = []
    for i in range(len(segments) - 1):
        row_a = segments.iloc[i]
        row_b = segments.iloc[i + 1]
        path_data.append({
            "path": [[row_a["lon"], row_a["lat"]], [row_b["lon"], row_b["lat"]]],
            "color": _pace_to_color(row_a["pace_sec_per_km"], p_min, p_max),
        })
 
    path_layer = pdk.Layer(
        "PathLayer", data=path_data, get_path="path", get_color="color",
        width_min_pixels=5, pickable=False,
    )
 
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
 
 
def _render_elevation_profile(segments, marker_idx):
    """Höhenprofil, eingefärbt nach Pace wie die Karte, mit vertikaler
    Linie + Punkt an der Slider-Position (nutzt denselben marker_idx wie
    die Karte, dadurch bewegen sich beide automatisch synchron)."""
    
 
    p_min = segments["pace_sec_per_km"].min()
    p_max = segments["pace_sec_per_km"].max()
 
    x_km = segments["mid_m"] / 1000.0
    y_ele = segments["ele"]
 
    fig = go.Figure()
 # Y-Achsen-Range vorab berechnen, statt bis 0 zu gehen (waere bei
    # typischen Hoehenwerten weit ausserhalb des sichtbaren Bereichs)
    ele_min = y_ele.min()
    ele_max = y_ele.max()
    ele_span = max(ele_max - ele_min, 1.0)  # mind. 1m, falls komplett flach
    padding = ele_span * 0.6
    y_axis_bottom = ele_min - padding
    y_axis_top = ele_max + padding

    # Flaeche unter der Linie, Baseline am unteren Achsenrand statt bei 0
    # (sonst quetscht die Auto-Skalierung die Hoehenlinie nach oben)
    fig.add_trace(go.Scatter(
        x=x_km, y=[y_axis_bottom] * len(x_km),
        mode="lines", line=dict(width=0),
        showlegend=False, hoverinfo="skip",
    ))
    fig.add_trace(go.Scatter(
        x=x_km, y=y_ele, mode="lines",
        line=dict(width=0), fill="tonexty",
        fillcolor="rgba(120,120,120,0.10)",
        showlegend=False, hoverinfo="skip",
    ))
    # Hoehenlinie aus vielen kurzen Teilstuecken, da Plotly keinen
    # Farbverlauf pro Punkt fuer eine einzelne Linie kann
    for i in range(len(segments) - 1):
        color = _pace_to_color(segments["pace_sec_per_km"].iloc[i], p_min, p_max)
        color_str = f"rgb({color[0]},{color[1]},{color[2]})"
        fig.add_trace(go.Scatter(
            x=[x_km.iloc[i], x_km.iloc[i + 1]],
            y=[y_ele.iloc[i], y_ele.iloc[i + 1]],
            mode="lines",
            line=dict(color=color_str, width=4),
            showlegend=False,
            hoverinfo="skip",
        ))
 
    # Fläche unter der Linie (dezent, für den "Bergprofil"-Look)
    fig.add_trace(go.Scatter(
        x=x_km, y=y_ele, mode="lines",
        line=dict(width=0), fill="tozeroy",
        fillcolor="rgba(120,120,120,0.10)",
        showlegend=False, hoverinfo="skip",
    ))
 
    # Vertikale Linie + Punkt an der aktuellen Slider-Position
    marker_row = segments.iloc[marker_idx]
    fig.add_vline(
        x=marker_row["mid_m"] / 1000.0,
        line_width=2, line_dash="dash", line_color="rgb(30,30,220)",
    )
    fig.add_trace(go.Scatter(
        x=[marker_row["mid_m"] / 1000.0], y=[marker_row["ele"]],
        mode="markers",
        marker=dict(size=12, color="rgb(30,30,220)"),
        showlegend=False, hoverinfo="skip",
    ))
 
    fig.update_layout(
        height=400,
        margin=dict(l=10, r=10, t=10, b=10),
        xaxis_title="Distanz (km)",
        yaxis_title="Höhe (m)",
        yaxis=dict(range=[y_axis_bottom, y_axis_top]),
        plot_bgcolor="rgba(0,0,0,0)",
    )
 
    with st.container(key="elevation_profile_chart"):
        st.html(
            """
            <style>
            .st-key-elevation_profile_chart [data-testid="stPlotlyChart"] {
                border-radius: 16px;
                overflow: hidden;
            }
            </style>
            """
        )
        st.plotly_chart(fig, use_container_width=True)
