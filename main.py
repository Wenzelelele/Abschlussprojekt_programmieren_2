import streamlit as st

from pages.profil import (init_login_state,login_page,register_page,logout_button,show_profile)

from functions.user_profil import create_user_file  # erstellt die users.csv, falls sie fehlt

st.set_page_config(page_title= "Bergläufer Dashboard", page_icon="⛰️",layout="wide") 

create_user_file()      # erstellt users.csv falls nötig
init_login_state()      # erstellt logged_in, current_user und page

col_left, col_right= st.columns([6,1])

with col_right:
    with st.popover("Support"):
        st.write("Kundenservice 24/7")
        st.write("E-Mail: bergläufer24@gmail.com")
        st.write("Telefon: +43 664 12345678")

if not st.session_state.logged_in:        #wenn niemand eingeloggt ist

    if st.session_state.page == "login":  #wenn Login-Seite aktiv ist
        login_page()                      #Login-Seite anzeigen

    elif st.session_state.page == "register":  #wenn Registrierungsseite aktiv ist
        register_page()                        #Registrierungsseite anzeigen

else:
    logout_button()  
    st.sidebar.title("Navigation")      #Titel in der Sidebar

    selected_page = st.sidebar.radio(   #Auswahlmenü in der Sidebar
        "Seite auswählen",
        ["Profil", "Training", "Analyse"])

    if selected_page == "Profil":   #wenn Profil ausgewählt wurde
        show_profile()              #Profil anzeigen
