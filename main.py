import streamlit as st

from functions.ui_theme import apply_custom_theme
from functions.user_profil import create_user_file
from views.profil import (
    init_login_state,
    login_page,
    logout_button,
    register_page,
    show_profile,
)
from views.route_tab import render_route_tab
from views.training_tab import render_training_tab

st.set_page_config(
    page_title="Berglaeufer Dashboard", page_icon=":mountain:", layout="wide"
)
apply_custom_theme()


def init_route_test_data():
    """Platzhalter-Trainingsdaten, falls noch keine echten hochgeladen wurden -
    damit der Route-Tab auch ohne Trainingsdaten-Tab lauffähig ist."""
    if "pace_hr_bins" not in st.session_state:
        st.session_state["pace_hr_bins"] = {
            "up": {"Z1": 380, "Z2": 350, "Z3": 330, "Z4": 310, "Z5": 290},
            "flat": {"Z1": 360, "Z2": 330, "Z3": 310, "Z4": 290, "Z5": 270},
            "down": {"Z1": 340, "Z2": 310, "Z3": 290, "Z4": 270, "Z5": 250},
        }
        st.session_state["ef_up"] = 0.95
        st.session_state["ef_flat"] = 1.10
        st.session_state["ef_down"] = 1.20
        st.session_state["max_distance_km"] = 10.0
        # markiert fuer den Route-Tab: Mock statt echter Daten
        st.session_state["training_data_source"] = "mock"


def route_page():
    init_route_test_data()
    render_route_tab()


def training_tab():
    render_training_tab()


def _render_top_bar(show_info: bool) -> None:
    """Support-Kontakt oben rechts, mit Info-Button davor - der Info-Button
    nur wenn show_info=True (soll nur im Route-Tab sichtbar sein)."""
    if show_info:
        _, info_col, support_col = st.columns([5.3, 0.7, 1])
        with info_col:
            st.button(
                "ℹ️",
                key="route_tab_info",
                help=(
                    "Route-Tab: Wähle eine Strecke (Beispiel, gespeichert oder "
                    "eigene GPX-Datei hochladen). Gib eine Ziel-HF-Zone ODER eine "
                    "Zielzeit an - die jeweils andere wird automatisch berechnet. "
                    "Karte und Höhenprofil zeigen die prognostizierte Pace "
                    "farbcodiert (rot = schnell, grün = langsam) entlang der "
                    "Strecke. Unten siehst du die Gesamtzeit-Prognose, rechts "
                    "kannst du das Ergebnis als FIT-Workout für Garmin-Geräte "
                    "herunterladen."
                ),
            )
    else:
        _, support_col = st.columns([6, 1])

    with support_col:
        with st.popover("Support"):
            st.write("Kundenservice 24/7")
            st.write("E-Mail: bergläufer24@gmail.com")
            st.write("Telefon: +43 664 12345678")

        st.image("data/berglaeufer_logo_transparent.png", width=80)


create_user_file()
init_login_state()

if not st.session_state.logged_in:
    _render_top_bar(show_info=False)

    if st.session_state.page == "login":
        login_page()
    elif st.session_state.page == "register":
        register_page()

else:
    pg = st.navigation(
        [
            st.Page(show_profile, title="Profil"),
            st.Page(training_tab, title="Trainingsdaten"),
            st.Page(route_page, title="Route"),
        ],
        position="sidebar",
    )

    _render_top_bar(show_info=(pg.title == "Route"))

    st.sidebar.image("data/berglaeufer_logo_transparent.png", width=180)
    logout_button()

    pg.run()

# if __name__ == "__main__":
# main()
