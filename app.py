import streamlit as st

st.set_page_config(
    page_title="Dashboard Météo Alice",
    layout="wide",
    page_icon="🌈"
)
import pandas as pd
import requests
import time
import plotly.express as px

# Chargement des variables d'environnement à partir du fichier .toml

CLIENT_ID = st.secrets["NETATMO_CLIENT_ID"]
CLIENT_SECRET = st.secrets["NETATMO_CLIENT_SECRET"]
REFRESH_TOKEN = st.secrets["NETATMO_REFRESH_TOKEN"]

# Titre de l'application
st.title('🌈 DashBoard Météo Alice')
st.divider()
# Récupération des données de l'API Netatmo

# Récupération d'un access token frais (valable ~3h)
@st.cache_data(ttl=10000)
def get_access_token():
    r = requests.post("https://api.netatmo.com/oauth2/token", data={
        "grant_type": "refresh_token",
        "refresh_token": REFRESH_TOKEN,
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
    })
    r.raise_for_status()
    return r.json()["access_token"]


# Récupération des données de la station (1 appel max toutes les 10 min)
@st.cache_data(ttl=600)
def get_station_data():
    headers = {"Authorization": f"Bearer {get_access_token()}"}
    r = requests.get("https://api.netatmo.com/api/getstationsdata", headers=headers)
    r.raise_for_status()
    return r.json()

try:
    data = get_station_data()
except requests.exceptions.RequestException:
    st.error("❌ Impossible de récupérer les données Netatmo. Réessaie dans quelques minutes.")
    st.stop()

# Historique des mesures (Directement chez Netatmo)
@st.cache_data(ttl=1800)
def get_historique(device_id, types, module_id=None, jours=2, scale="30min"):
    fin = int(time.time())
    params = {
        "device_id": device_id,
        "scale": scale,
        "type": ",".join(types),
        "date_begin": fin - jours * 86400,
        "date_end": fin,
        "optimize": "false",
    }
    if module_id:
        params["module_id"] = module_id

    headers = {"Authorization": f"Bearer {get_access_token()}"}
    r = requests.get("https://api.netatmo.com/api/getmeasure", headers=headers, params=params)
    r.raise_for_status()

    body = r.json()["body"]
    df = pd.DataFrame.from_dict(body, orient="index", columns=types)
    df.index = pd.to_datetime(df.index.astype(int), unit="s", utc=True).tz_convert("Europe/Paris")
    return df.sort_index().reset_index(names="date")


# Extraction des données principales
etat_station = data["status"]
main_device = data["body"]["devices"][0]
date_mesure = pd.to_datetime(
    main_device["dashboard_data"]["time_utc"], unit="s", utc=True
).tz_convert(main_device["place"]["timezone"])


# Extraction des données des différents modules
salon = main_device["dashboard_data"]
salon_info = main_device["place"]
timezone = main_device["place"]["timezone"]

# Identification des modules par type (et non par position)
modules = {m["type"]: m for m in main_device["modules"]}

module_jardin = modules.get("NAModule1")
module_pluvio = modules.get("NAModule3")

if not module_jardin or "dashboard_data" not in module_jardin:
    st.error("❌ Module Jardin injoignable (pile ou connexion ?)")
    st.stop()

if not module_pluvio or "dashboard_data" not in module_pluvio:
    st.error("❌ Pluviomètre injoignable (pile ou connexion ?)")
    st.stop()

jardin = module_jardin["dashboard_data"]
pluvio = module_pluvio["dashboard_data"]

# Extraction des données du module Salon
temperature_int = salon["Temperature"]
humidite_int = salon["Humidity"]
co2 = salon["CO2"]
bruit = salon["Noise"]
pression_int = salon["Pressure"]
temperature_int_min = salon.get("min_temp", temperature_int)
temperature_int_max = salon.get("max_temp", temperature_int)
tendance_temperature_int = salon.get("temp_trend")
tendance_pression = salon.get("pressure_trend")
altitude = salon_info["altitude"]
ville = salon_info["city"]


# Extraction des données du module Jardin
temperature_jardin = jardin["Temperature"]
humidite_jardin = jardin["Humidity"]
temperature_min_jardin = jardin.get("min_temp", temperature_jardin)
temperature_max_jardin = jardin.get("max_temp", temperature_jardin)
tendance_temperature_jardin = jardin.get("temp_trend")
batterie_jardin = module_jardin["battery_percent"]

# Extraction des données du module Pluvio
pluie = pluvio.get("Rain", 0)
total_pluie = pluvio.get("sum_rain_24", 0)
pluie_1h = pluvio.get("sum_rain_1", 0)
batterie_pluvio = module_pluvio["battery_percent"]

# Fonctions des tendances et des graphiques 
def afficher_tendance_temperature(tendance):
    if tendance == "up":
        return "📈 Tendance : hausse"
    elif tendance == "down":
        return "📉 Tendance : baisse"
    else:
        return "➡️ Tendance : stable"


def afficher_tendance_pression(tendance):
    if tendance == "up":
        return "☀️ Amélioration météo probable"
    elif tendance == "down":
        return "🌧️ Dégradation météo probable"
    else:
        return "➡️ Situation stable"

def afficher_graph(df, y, titre, axe_y, type_graph="line", zone=None):
    if df is None:
        return
    trace = px.bar if type_graph == "bar" else px.line
    fig = trace(df, x="date", y=y, title=titre)

    # Zone de confort
    if zone:
        fig.add_hrect(
            y0=zone[0], y1=zone[1],
            fillcolor="lightgreen", opacity=0.2, line_width=0
        )
    fig.update_layout(xaxis_title=None, yaxis_title=axe_y, hovermode="x unified")
    fig.update_xaxes(tickformat="%d/%m %Hh")
    st.plotly_chart(fig, width="stretch")

# =====================================
# Sidebar
st.sidebar.title("ℹ️ Informations Station")

# Etat de la station
if etat_station == "ok":
    st.sidebar.success("✅ Station en ligne")

st.sidebar.header("🕒 Dernière mesure")

st.sidebar.write(
date_mesure.strftime("%d/%m/%Y à %H:%M")
)
st.sidebar.write(f"Fuseau horaire : {timezone}")

st.sidebar.divider()

# Calcul du nombre d'alertes
nb_alertes = 0

# CO2
if co2 > 800:
    nb_alertes += 1

# Température intérieure
if temperature_int > 25 or temperature_int < 18:
    nb_alertes += 1

# Humidité intérieure
if humidite_int > 70 or humidite_int < 40:
    nb_alertes += 1

# Humidité extérieure
if humidite_jardin > 95 or humidite_jardin < 30:
    nb_alertes += 1

# Température extérieure
if temperature_jardin > 30 or temperature_jardin < 5:
    nb_alertes += 1

# Bruit
if bruit > 70 :
    nb_alertes += 1

# Alertes
st.sidebar.header("🚨 Alertes en cours")

st.sidebar.metric(
    label="Nombre d'alertes",
    value=nb_alertes
)

if nb_alertes == 0:
    st.sidebar.success("Tout est normal")

elif nb_alertes <= 1:
    st.sidebar.warning("Un point à surveiller")

elif nb_alertes <= 3:
    st.sidebar.warning("Quelques points à surveiller")

else:
    st.sidebar.error("Attention")

st.sidebar.divider()

# Données du lieu de la station
st.sidebar.header("🌏 Lieu de la station")

st.sidebar.write(f"📍{ville}")
st.sidebar.write(f"🗺️ France")
st.sidebar.write(f"🎢 Altitude : {altitude} m")

st.sidebar.divider()

# Données des capteurs
st.sidebar.header("🔋 État des capteurs")

st.sidebar.write(f"🌳 Jardin : {batterie_jardin}%")
st.sidebar.write(f"🌧️ Pluvio : {batterie_pluvio}%")
# =====================================

# =====================================
# Détail des alertes

if nb_alertes > 0:

    with st.container(border=True):

        st.header("🚨 Alertes", text_alignment="center")

        col1, col2, col3 = st.columns(3)

        with col1:
            if co2 > 1000:
                st.error(
                    "🚨 **CO₂ élevé**  \n"
                    "*🚩 Aération nécessaire*"
                )

            elif co2 > 800:
                st.warning("⚠️ Pensez à aérer")

        with col2:
            if temperature_int > 28:
                st.error(
                    "🥵 **Intérieur trop chaud**  \n"
                    "*🚩 Ventilation ou climatisation à activer*"
                )

            elif temperature_int > 25:
                st.warning(
                    "☀️ **Intérieur chaud**  \n"
                    "*💭 Pensez à baisser les volets*"
                )

            elif temperature_int < 18:
                st.warning("🥶 **Intérieur frais**")

        with col3:
            if humidite_int > 70:
                st.warning("💧 **Humidité intérieure élevée**")

            elif humidite_int < 40:
                st.warning("🏜️ **Air intérieur trop sec**")

        col4, col5, col6 = st.columns(3)

        with col4:
            if humidite_jardin > 95:
                st.warning("🌫️ **Humidité extérieure très élevée**")

            elif humidite_jardin < 30:
                st.warning("🏜️ **Air extérieur très sec**")

        with col5:
            if temperature_jardin > 35:
                st.error("🥵 **Forte chaleur**")

            elif temperature_jardin > 30:
                st.warning("☀️ **Température élevée**")

            elif temperature_jardin < 0:
                st.error("🧊 **Risque de gel**")

            elif temperature_jardin < 5:
                st.warning("❄️ **Température basse**")

        with col6:
            if bruit > 70:
                st.warning("🔊 **Niveau sonore élevé**")

# =====================================

# =====================================
# Données Maison
st.header("🏠 Données Maison",text_alignment= "center")
st.write("")
st.write("")
st.write("")

col1, col2, col3, col4 = st.columns(4)

with col1:

    st.metric(
        label="Température Salon",
        value=f"🌡️ {temperature_int} °C"
    )

    st.caption(afficher_tendance_temperature(tendance_temperature_int))
    st.caption(
        f"🔵 {temperature_int_min} °C | 🔴 {temperature_int_max} °C"
    )

with col2:
    st.metric(label="Humidité Intérieure", value=f"💧{humidite_int} %")

with col3:
    st.metric(label="CO\u2082 Intérieur", value=f"🫁{co2} ppm")

with col4:
    st.metric(label="Volume Intérieur", value=f"🔉{bruit} dB")



# Graphs interieurs
try:
    df_int = get_historique(main_device["_id"], ["temperature", "pressure", "humidity", "co2", "noise"])
except requests.exceptions.RequestException:
    st.error("❌ Historique intérieur indisponible pour le moment.")
    df_int = None

col1, col2 = st.columns(2)

with col1:
# Graph temp interieure
    afficher_graph(df_int, "temperature", "Température intérieure (48h)", "Température (°C)", zone=(18, 25))

with col2:
# Graph CO2
    afficher_graph(df_int, "co2", "CO\u2082 (48h)", "CO\u2082 (ppm)", zone=(400, 800))

col3, col4 = st.columns(2)

with col3:
# Graph humidité interieure
    afficher_graph(df_int, "humidity", "Humidité intérieure (48h)", "Humidité (%)", zone=(40, 70))

with col4:
# Graph Bruit
    afficher_graph(df_int, "noise", "Volume intérieur (48h)", "Volume (dB)", zone=(35, 60))

# =====================================

# =====================================
# Données Jardin
st.divider()
st.header("🌳 Données Jardin",text_alignment= "center")
st.write("")
st.write("")
st.write("")
col1, col2, col3, col4 = st.columns(4)

with col1:

    st.metric(
        label="Température Jardin",
        value=f"🌡️ {temperature_jardin} °C"
    )

    st.caption(afficher_tendance_temperature(tendance_temperature_jardin))

    st.caption(
        f"🔵 {temperature_min_jardin} °C | 🔴 {temperature_max_jardin} °C"
    )

with col2:
    st.metric(label="Humidité Jardin", value=f"💧{humidite_jardin} %")

with col3:
    st.metric(label="Pluie", value=f"🌧️{pluie} mm")
    st.caption(
        f"💦 Auj. : {total_pluie} mm | 💦 1h : {pluie_1h} mm"
    )

with col4:

    st.metric(
        label="Pression",
        value=f"🌤️ {pression_int} hPa"
    )

    st.caption(afficher_tendance_pression(tendance_pression)) 

# Graphs exterieurs
try:
    df_ext = get_historique(main_device["_id"], ["temperature", "humidity"], module_id=module_jardin["_id"])
except requests.exceptions.RequestException:
    st.error("❌ Historique extérieur indisponible pour le moment.")
    df_ext = None

col1, col2 = st.columns(2)


with col1:
# Graph temp exterieure
    afficher_graph(df_ext, "temperature", "Température extérieure (48h)", "Température (°C)")    

with col2:
# Graph humidité exterieure
    afficher_graph(df_ext, "humidity", "Humidité extérieure (48h)", "Humidité (%)") 


col3, col4 = st.columns(2)

with col3:
# Graph pression
    afficher_graph(df_int, "pressure", "Pression Atmosphérique (48h)", "Pression (hPa)")

with col4:
# Graph pluie
    try:
        df_pluie = get_historique(main_device["_id"], ["rain"], module_id=module_pluvio["_id"])
    except requests.exceptions.RequestException:
        st.error("❌ Historique pluviomètre indisponible pour le moment.")
        df_pluie = None

    if df_pluie is not None and df_pluie["rain"].sum() == 0:
        st.info("☀️ Aucune pluie sur les dernières 48h")
    else:
        afficher_graph(df_pluie, "rain", "Précipitations par demi-heure (48h)", "Pluie (mm)", type_graph="bar")