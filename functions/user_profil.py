import pandas as pd
import os

user_file= "users.csv"                      #Pfad zur Datei wo alle Nutzer gespeichert sind 

NEW_PROFILE_COLUMNS = {                     #zusätzliche Profilfelder für HF Zonen
    "zone_method": "max_hr",
    "hr_bound_1": None,
    "hr_bound_2": None,
    "hr_bound_3": None,
    "hr_bound_4": None}

def create_user_file():                     #erstellt eine User CSV falls sie noch nicht vorhanden ist
    if not os.path.exists("data"):          #prüft ob es den Ordner data schon gibt
        os.makedirs("data")                 #fügt einen Ordner data hinzu

    if not os.path.exists(user_file):       #prüft pb die users.csv existiert
        df= pd.DataFrame(columns=[          #erstellt leere Tabelle mit Spalten
            "username",
            "password",
            "name",
            "age",
            "height",
            "weight",
            "level",
            "max_hr",
            "zone_method",
            "hr_bound_1",
            "hr_bound_2",
            "hr_bound_3",
            "hr_bound_4"])
          
    
        df.to_csv(user_file, index=False)   #speichert die leere Tabelle in der CSV 

def load_users():                           #alle User von der CSV werden geladen
    create_user_file()                      #prüft ob ordner und datei existieren
    #username/password als str einlesen, sonst macht pandas z.B. aus "1234" eine Zahl
    #und der Vergleich mit der Texteingabe aus st.text_input schlägt immer fehl
    users = pd.read_csv(user_file, dtype={"username": str, "password": str})
    for column, default_value in NEW_PROFILE_COLUMNS.items(): #prüft ob die neuen spalten bereits vorhanden sind
        if column not in users.columns: #Fehlende Spalte wird ergänzt
            users[column] = default_value
    return users

def save_users(username,password,name,age,height,weight,level,max_hr,zone_method="max_hr",hr_bound_1=None,hr_bound_2=None,hr_bound_3=None,hr_bound_4=None):
    users= load_users()                     

    new_user= pd.DataFrame([{               #erstellt eine neue kleine Tabelle mit genau einem Benutzer
        "username": username,
        "password": password,
        "name": name,
        "age": age,
        "height": height,
        "weight": weight,
        "level": level,
        "max_hr": max_hr,
        "zone_method": zone_method,         #zonen für hannes relevant
        "hr_bound_1": hr_bound_1,
        "hr_bound_2": hr_bound_2,
        "hr_bound_3": hr_bound_3,
        "hr_bound_4": hr_bound_4}])
    
    users= pd.concat([users, new_user], ignore_index=True) #hängt neuen Benutzer an die Tabelle an
    users.to_csv(user_file, index=False)                   #speichert komplette Tabelle wieder in CSV

def check_login(username, password):                                      #prüft ob Passwort eingabe korrekt ist
    users= load_users()                                 
    user=users[(users["username"]== username) &
               (users["password"]== password)]
    return len(user) > 0                                #gibt True zurück falls ein passender Nutzer gefunden wurde

def username_exists(username):                                  #checkt ob Usernames schon vergeben sind
    users=load_users()
    return username in users["username"].values

def get_user_data(username):
    users = load_users()
    user = users[users["username"] == username]  #wie ein Filter, sucht die Zeile mit dem passenden Benutzernamen
    
    if len(user)>0:                              #prüft ob nutzer gefunden wurde
        return user.iloc[0]                      #gibt passende Nutzerzeile zurück
    return None                                  #falls kein Nutzer gefunden wurde, None wird zurückgegeben

def update_user_data(username, name, age, height, weight, level, max_hr): #falls im Profil Daten ändern will
    users = load_users()
    user_index = users["username"] == username

    if not user_index.any():
        return False

    users.loc[user_index, "name"] = name
    users.loc[user_index, "age"] = age
    users.loc[user_index, "height"] = height
    users.loc[user_index, "weight"] = weight
    users.loc[user_index, "level"] = level
    users.loc[user_index, "max_hr"] = max_hr

    users.to_csv(user_file, index=False) #aktuell eingegebene Werte werden gespeichert 
    return True

def update_zone_settings(
    username,
    zone_method,
    hr_bound_1=None,
    hr_bound_2=None,
    hr_bound_3=None,
    hr_bound_4=None):

    users = load_users() #alle nutzer laden

    user_index = users["username"] == username #aktuellen nutzer suchen

    if not user_index.any(): #wieder überprüfen ob nutzer existiert
        return False
    
    users.loc[user_index, "zone_method"] = zone_method #Zonen Methoden aktualisieren 
    users.loc[user_index, "hr_bound_1"] = hr_bound_1
    users.loc[user_index, "hr_bound_2"] = hr_bound_2
    users.loc[user_index, "hr_bound_3"] = hr_bound_3
    users.loc[user_index, "hr_bound_4"] = hr_bound_4

    users.to_csv(user_file, index=False)#Änderungen werden einfach in der CSV gespeichert 

    return True