"""
test_app.py
-----------
Wrapper zum Testen von route_tab.py mit Mock-Daten in st.session_state,
so wie es der "data"-Baustein liefern wuerde.
"""

import streamlit as st
from pages.route_tab import render_route_tab

if "pace_hr_bins" not in st.session_state:
    st.session_state["pace_hr_bins"] = {
        "up":   {"Z1": 380, "Z2": 350, "Z3": 330, "Z4": 310, "Z5": 290},
        "flat": {"Z1": 360, "Z2": 330, "Z3": 310, "Z4": 290, "Z5": 270},
        "down": {"Z1": 340, "Z2": 310, "Z3": 290, "Z4": 270, "Z5": 250},
    }
    st.session_state["ef_up"] = 0.95
    st.session_state["ef_flat"] = 1.10
    st.session_state["ef_down"] = 1.20
    st.session_state["max_distance_km"] = 10.0

render_route_tab()
