import streamlit as st

from functions.user_profil import create_user_file
from views.profil import (
    init_login_state,
    login_page,
    logout_button,
    register_page,
    show_profile,
)
from views.route_tab import render_route_tab

st.set_page_config(
    page_title="Berglaeufer Dashboard",
    page_icon=":mountain:",
    layout="wide",
)


def init_route_test_data():
    """
    Platzhalter fuer den echten "data"-Baustein: legt Mock-Trainingsdaten
    in st.session_state an, damit der Route-Tab lauffaehig ist. Sobald die
    echte Datenpipeline steht, wird hier stattdessen deren Ergebnis in
    dieselben session_state-Keys geschrieben (siehe Doku in route_tab.py).
    """
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


def route_page():
    init_route_test_data()
    render_route_tab()


create_user_file()
init_login_state()

if not st.session_state.logged_in:
    if st.session_state.page == "login":
        login_page()
    elif st.session_state.page == "register":
        register_page()

else:
    logout_button()

    pg = st.navigation(
        [
            st.Page(show_profile, title="Profil"),
            st.Page(route_page, title="Route"),
        ],
        position="sidebar",
    )
    pg.run()
