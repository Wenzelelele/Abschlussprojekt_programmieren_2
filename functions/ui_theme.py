"""
ui_theme.py
-----------
Optisches Feintuning für das Dashboard: ein Berg-Panorama als Hintergrund
(als eingebettetes SVG) plus längliche,
pillenförmige Sidebar-Navigation. Wird per CSS-Injektion umgesetzt, da
Streamlit selbst kein Hintergrundbild über config.toml erlaubt.
"""

import base64

import streamlit as st


_MOUNTAIN_SVG = """
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1600 900" preserveAspectRatio="xMidYMid slice">
  <defs>
    <linearGradient id="sky" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0%" stop-color="#fdf1de"/>
      <stop offset="45%" stop-color="#f6c9a0"/>
      <stop offset="100%" stop-color="#c9d8e3"/>
    </linearGradient>
    <radialGradient id="sun" cx="50%" cy="50%" r="50%">
      <stop offset="0%" stop-color="#fff3d6" stop-opacity="0.95"/>
      <stop offset="100%" stop-color="#fff3d6" stop-opacity="0"/>
    </radialGradient>
  </defs>

  <rect width="1600" height="900" fill="url(#sky)"/>
  <circle cx="1230" cy="230" r="140" fill="url(#sun)"/>
  <circle cx="1230" cy="230" r="55" fill="#fff6e2" opacity="0.9"/>

  <polygon fill="#b9c9d6" opacity="0.85"
    points="0,900 0,550 150,480 300,520 450,430 600,500 750,420 900,480
            1050,400 1200,470 1350,410 1500,460 1600,430 1600,900"/>

  <polygon fill="#8ea2b4" opacity="0.9"
    points="0,900 0,650 120,560 280,620 420,520 580,600 720,500 880,580
            1020,480 1180,560 1320,470 1480,540 1600,500 1600,900"/>

  <polygon fill="#4f6273"
    points="0,900 0,750 100,650 250,720 380,600 520,700 650,580 800,680
            950,560 1100,660 1250,570 1400,650 1550,600 1600,650 1600,900"/>

  <g fill="#eef4f8" opacity="0.9">
    <polygon points="380,600 410,635 350,635"/>
    <polygon points="650,580 680,615 620,615"/>
    <polygon points="950,560 985,600 918,600"/>
    <polygon points="1250,570 1280,605 1220,605"/>
  </g>
</svg>
"""


def _svg_data_uri() -> str:
    encoded = base64.b64encode(_MOUNTAIN_SVG.strip().encode("utf-8")).decode("utf-8")
    return f"data:image/svg+xml;base64,{encoded}"


def apply_custom_theme() -> None:
    """Injiziert Berg-Hintergrund + Sidebar-Pillen-Navigation als CSS."""
    background = _svg_data_uri()

    st.markdown(
        f"""
        <style>
        .stApp {{
            background-image: url("{background}");
            background-size: cover;
            background-position: center;
            background-attachment: fixed;
        }}

        [data-testid="stAppViewContainer"] > .main {{
            background-color: rgba(247, 244, 238, 0.85);
            backdrop-filter: blur(6px);
            border-radius: 18px;
            padding: 1.5rem 2rem;
            margin: 1rem;
        }}

        [data-testid="stSidebar"] {{
            background-color: rgba(24, 33, 41, 0.55);
            backdrop-filter: blur(10px);
        }}

        [data-testid="stSidebar"] * {{
            color: #f5f1e8;
        }}

        /* Eingabefelder haben einen hellen eigenen Hintergrund - dort muss
           der Text dunkel bleiben, sonst ist er auf hell/hell unsichtbar. */
        [data-testid="stSidebar"] input,
        [data-testid="stSidebar"] textarea,
        [data-testid="stSidebar"] [data-baseweb="select"] * {{
            color: #20262b;
        }}

        [data-testid="stSidebarNav"] a {{
            display: block;
            margin: 0.35rem 0.9rem;
            padding: 0.65rem 1.1rem;
            border-radius: 999px;
            background-color: rgba(255, 255, 255, 0.08);
            font-weight: 500;
            transition: background-color 0.15s ease;
        }}

        [data-testid="stSidebarNav"] a:hover {{
            background-color: rgba(255, 255, 255, 0.2);
        }}

        [data-testid="stSidebarNav"] a[aria-current="page"] {{
            background-color: rgba(255, 255, 255, 0.3);
            font-weight: 700;
        }}

        [data-testid="stSidebar"] button {{
            border-radius: 999px;
            width: 100%;
        }}
        </style>
        """,
        unsafe_allow_html=True,
    )
