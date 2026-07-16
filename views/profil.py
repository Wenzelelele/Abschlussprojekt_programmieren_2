import streamlit as st

from functions.user_profil import (check_login,save_users,username_exists,get_user_data,update_user_data) 

def init_login_state(): #bereitet login Zustand vor
    
    if "logged_in" not in st.session_state:
        st.session_state.logged_in = False

    if "current_user" not in st.session_state:
        st.session_state.current_user = None

    if "page" not in st.session_state:
        st.session_state.page = "login"

def login_page():
    st.title("Bergläufer Dashboard")
    st.caption("Dein persönlicher Begleiter für Berglauf und Training")

    #Drei Spalten erstellen und die mittlere enthält den Login
    col_left, col_center, col_right = st.columns([1, 1.5, 1])

    with col_center:
        with st.container(border=True):#erstellt Umrandete Login-Karte
            st.subheader("🔐 Login")
            st.write("Melde dich mit deinen Zugangsdaten an.")
            with st.form("login_form"): #Benutzername und Passwort gemeinsam absenden
                username = st.text_input(
                    "Benutzername",
                    placeholder="Benutzername eingeben")
                password = st.text_input(
                    "Passwort",
                    type="password",
                    placeholder="Passwort eingeben")

                login_clicked = st.form_submit_button(
                    "Einloggen",
                    type="primary",
                    use_container_width=True)

            # Auswertung nach dem Absenden
            if login_clicked:

                if check_login(username, password):

                    st.session_state.logged_in = True
                    st.session_state.current_user = username

                    st.rerun()
                else:
                    st.error("Benutzername oder Passwort ist falsch.")

            st.divider()

            st.markdown("**Noch kein Profil?**")
            st.caption("Erstelle kostenlos dein persönliches Läuferprofil.")

            if st.button(
                "Profil erstellen",
                use_container_width=True):
                st.session_state.page = "register"
                st.rerun()

    st.divider() 

def register_page(): 
    st.title("Neues Profil erstellen")
    username= st.text_input("Benutzername")
    password= st.text_input("Password",type= "password")
    password_repeat= st.text_input("Password wiederholen", type="password")

    st.subheader("Persönliche Daten")
    
    name= st.text_input("Name")
    age= st.number_input("Alter", min_value=10, max_value=100, step=1)
    height= st.number_input("Größe", min_value=130, max_value=230, step=1)
    weight= st.number_input("Gewicht", min_value=40, max_value=200, step=1)
    level= st.selectbox("Leistungsniveau",["Anfänger", "Fortgeschritten", "Profi"])
    max_hr= st.number_input("Maximale Herzfrequenz", min_value=100, max_value=220, step=1)

    if st.button("Profil speichern"):  # Button zum Speichern

        if username == "" or password == "" or name == "":#prüft Pflichtfelder
            st.warning("Bitte fülle Benutzername, Passwort und Name aus.")

        elif password != password_repeat:#prüft, ob Passwörter gleich sind
            st.error("Die Passwörter stimmen nicht überein.")
        
        elif username_exists(username):#prüft, ob Benutzername schon existiert
            st.error("Dieser Benutzername existiert bereits.")
        
        else:
            save_users(username, password, name, age, height, weight, level, max_hr)  #Benutzer speichern
            st.success("Profil wurde erfolgreich erstellt!")  #Erfolgsmeldung
            st.session_state.logged_in = True                 #direkt einloggen
            st.session_state.current_user = username          #Benutzer merken
            st.rerun()  

    st.divider()#Trennlinie

    if st.button("Zurück zum Login"):                         #zurück zur Login-Seite
        st.session_state.page = "login"
        st.rerun()

def logout_button(): #Button zum ausloggen
    if st.sidebar.button("Logout"):            
        st.session_state.logged_in = False      #Benutzer ist nicht mehr eingeloggt
        st.session_state.current_user = None    #aktueller Benutzer wird gelöscht
        st.session_state.page = "login"         #App springt zurück zur Login-Seite
        st.rerun() 

def show_profile(): #zeigt das Profil 
    
    user = get_user_data(st.session_state.current_user)  #lädt die Daten des aktuell eingeloggten Benutzers

    if st.session_state.pop("profile_updated", False):
        st.success("Deine Profildaten wurden erfolgreich aktualisiert.")

    if user is None:  # prüft, ob kein Benutzer gefunden wurde
        st.error("Benutzer konnte nicht gefunden werden.")  
        return    
    
    height_m = float(user["height"]) / 100 #Berechnung BMI
    bmi = float(user["weight"]) / (height_m ** 2)

    #BMI grob einordnen bzw grobe Bewertung und entsprechendes Signal dazu, könnte man theoretisch auch eine eigene Funktion dazu schreiben 
    if bmi < 18.5:
        bmi_status = "Untergewicht"
        bmi_message = st.info
    elif bmi < 25:
        bmi_status = "Normalbereich"
        bmi_message = st.success
    elif bmi < 30:
        bmi_status = "Übergewicht"
        bmi_message = st.warning
    else:
        bmi_status = "Adipositas"
        bmi_message = st.error
    
    st.title(f"Willkommen zurück, {user['name']}") #benutzerfreundliches Interface
    st.write("Hier findest du deine wichtigsten Profil- und Trainingsdaten auf einen Blick")

    st.divider() #trennlinie

    st.subheader("Athletenübersicht")

    col1, col2, col3 = st.columns(3)

    with col1:
        with st.container(border=True): #gestaltet wie eine Karte/Umriss
            st.markdown("🏔️ LEISTUNGSNIVEAU")
            st.metric(
            label="Aktuelles Level",
            value=user["level"])
            st.markdown("Deine aktuelle Selbsteinschätzung")

    with col2:
        with st.container(border=True):
            st.markdown("❤️ HERZFREQUENZ")
            st.metric(
            label="Maximale Herzfrequenz",
            value=f"{int(user['max_hr'])} bpm")
            st.markdown("Grundlage für deine Trainingszonen")

    with col3:
        with st.container(border=True):
            st.markdown("⚖️ KÖRPERDATEN")
            st.metric(
            label="Body-Mass-Index",
            value=f"{round(bmi, 1)}")
            st.markdown("Berechnet aus Größe und Gewicht")

    with st.container(border=True): #BMI Einordnung ebenso in einem Container angezeigt
        st.markdown("**📊 BMI-EINORDNUNG**")
        bmi_message(f"Dein BMI beträgt **{round(bmi, 1)}** – "f"grobe Einordnung: **{bmi_status}**")
    st.caption("Der BMI berücksichtigt beispielsweise Muskelmasse und " "Körperzusammensetzung nicht.")

    with st.expander("👤 Persönliche Daten anzeigen"):

        col1, col2 = st.columns(2)

        with col1:
            with st.container(border=True): #die sternchen machen schrift detulicher
                st.markdown("**👤 NAME**")
                st.subheader(user["name"])
                st.caption("Name des Athleten")

            with st.container(border=True):
                st.markdown("**📏 KÖRPERGRÖSSE**")
                st.subheader(f"{int(user['height'])} cm")
                st.caption("Gespeicherte Körpergröße")

        with col2:
            with st.container(border=True):
                st.markdown("**🎂 ALTER**")
                st.subheader(f"{int(user['age'])} Jahre")
                st.caption("Aktuelles Alter")

            with st.container(border=True):
                st.markdown("**⚖️ KÖRPERGEWICHT**")
                st.subheader(f"{int(user['weight'])} kg")
                st.caption("Gespeichertes Körpergewicht")

    with st.expander("✏️ Profil bearbeiten"): #einen weiteren Expander um Profil möglicherweise zu bearbeiten und Daten zu aktualisieren

        st.caption("Hier kannst du deine persönlichen Daten jederzeit aktualisieren.")

    # Formular verhindert, dass die Seite bei jeder Eingabe neu geladen wird
        with st.form("edit_profile_form"):

            col1, col2 = st.columns(2)

            with col1:
                new_name = st.text_input("Name",value=str(user["name"]))
                new_age = st.number_input("Alter",min_value=10,max_value=100,value=int(user["age"]),step=1)
                new_height = st.number_input("Größe in cm",min_value=130,max_value=230,value=int(user["height"]),step=1)

            with col2:
                new_weight = st.number_input("Gewicht in kg",min_value=40,max_value=200,value=int(user["weight"]),step=1)
                levels = ["Anfänger", "Fortgeschritten", "Profi"]
                # Aktuelle Position des Leistungsniveaus bestimmen
                current_level_index = levels.index(user["level"])
                new_level = st.selectbox("Leistungsniveau",levels,index=current_level_index)
                new_max_hr = st.number_input("Maximale Herzfrequenz",min_value=100,max_value=220,value=int(user["max_hr"]),step=1)

            save_changes = st.form_submit_button("Änderungen speichern",type="primary")

        if save_changes:

            if new_name.strip() == "":
                st.warning("Bitte gib einen Namen ein.")

            else:
                update_successful = update_user_data(
                    st.session_state.current_user,
                    new_name,
                    new_age,
                    new_height,
                    new_weight,
                    new_level,
                    new_max_hr)

                if update_successful:
                    st.session_state.profile_updated = True
                    st.rerun()

                else:
                    st.error("Die Änderungen konnten nicht gespeichert werden.")




