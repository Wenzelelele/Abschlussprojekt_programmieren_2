"""
training_tab.py
----------------
Streamlit-UI für den Trainingsdaten-Tab.
"""

import streamlit as st


def display_terrain(df, ef_factors: dict) -> None:
    """
    Zeigt die Effizienz-Tabelle/Charts für bergauf/flach/bergab.

    Input:  df - terrain-klassifizierter DataFrame
            ef_factors - {"up": .., "flat": .., "down": ..}
    Output: None (rendert Streamlit-Elemente)
    """
    raise NotImplementedError("TODO: st.bar_chart oder st.table mit ef_factors")


def generate_recommendation(ef_factors: dict) -> str:
    """
    Formuliert einen Trainingstipp basierend auf der schwächsten Geländeart.

    Input:  ef_factors - {"up": .., "flat": .., "down": ..}
    Output: Trainingsempfehlung als Text
    """
    raise NotImplementedError(
        "TODO: schwächsten Wert finden, passenden Text zurückgeben"
    )


def render_training_tab() -> None:
    """
    Einstiegspunkt für den Tab: Upload-Widget, ruft die Pipeline auf,
    schreibt Ergebnisse in st.session_state.
    """
    raise NotImplementedError(
        "TODO: st.file_uploader, TrainingData orchestrieren, session_state befüllen"
    )
