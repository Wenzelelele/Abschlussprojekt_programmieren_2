import streamlit as st

from functions.user_profil import (check_login,save_users,username_exists,get_user_data) 

def init_login_state(): #bereitet login Zustand vor
    
    if "logged_in" not in st.session_state:
        st.session_state.logged_in = False

    if "current_user" not in st.session_state:
        st.session_state.current_user = None

    if "page" not in st.session_state:
        st.session_state.page = "login"

def login_page():
    st.title("Bergläufer Dashboard")
    st.subheader("Login")
    username= st.text_input("Benutzername")
    password= st.text_input("Passwort", type="password")

    if st.button("Einloggen"):                                  #Button wird geklickt
        if check_login(username, password):                     
            st.session_state.logged_in = True                   #merkt sich: Benutzer ist eingeloggt
            st.session_state.current_user = username            #merkt sich den aktuellen Benutzer
            st.success("Login erfolgreich!")                    
            st.rerun()                                          #App neu laden
        else:
            st.error("Benutzername oder Passwort ist falsch.")  #Fehlermeldung

    st.divider() 

    st.write("Noch kein Profil?")  
    if st.button("Profil erstellen"):                           #Button zur Registrierung
        st.session_state.page = "register"                      #wechselt zur Register-Seite
        st.rerun()  

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

        if username == "" or password == "" or name == "":                          #prüft Pflichtfelder
            st.warning("Bitte fülle Benutzername, Passwort und Name aus.")

        elif password != password_repeat:                                           #prüft, ob Passwörter gleich sind
            st.error("Die Passwörter stimmen nicht überein.")
        
        elif username_exists(username):                                             #prüft, ob Benutzername schon existiert
            st.error("Dieser Benutzername existiert bereits.")
        
        else:
            save_users(username, password, name, age, height, weight, level, max_hr)  #Benutzer speichern
            st.success("Profil wurde erfolgreich erstellt!")  #Erfolgsmeldung
            st.session_state.logged_in = True                 #direkt einloggen
            st.session_state.current_user = username          #Benutzer merken
            st.rerun()  

    st.divider()                                              #Trennlinie

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

    if user is None:  # prüft, ob kein Benutzer gefunden wurde
        st.error("Benutzer konnte nicht gefunden werden.")  
        return    
    
    height_m = float(user["height"]) / 100
    bmi = float(user["weight"]) / (height_m ** 2)
    
    st.title(f"Willkommen zurück, {user['name']}") 

    col1, col2, col3 = st.columns(3)                    #erstellt 3 Spalten nebeneinander wie wir das schon in den Einheiten gemacht haben

    with col1: 
        st.metric("Name", user["name"])                 #zeigt den Namen als Kennzahl an
        st.metric("Alter", int(user["age"]))            #zeigt das Alter an

    with col2:  
        st.metric("Größe", f"{int(user['height'])} cm")  #zeigt die Größe mit Einheit cm 
        st.metric("Gewicht", f"{int(user['weight'])} kg")  #zeigt das Gewicht mit Einheit kg 

    with col3:  
        st.metric("Level", user["level"])  # zeigt das Leistungsniveau an
        st.metric("Max. Herzfrequenz", f"{int(user['max_hr'])} bpm")  # zeigt die maximale Herzfrequenz an
        st.metric("BMI", f"{round(bmi, 1)} kg/m²")


