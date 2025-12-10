# -*- coding: utf-8 -*-
"""
🌲 DASHBOARD FORESTAL INTEGRADO CON IA
Monitor Central: Sensores Ambientales + Detección de Disparos + Audio en Vivo
"""
import streamlit as st
import paho.mqtt.client as mqtt
from paho.mqtt.enums import CallbackAPIVersion
import json
import time
import pandas as pd
import numpy as np
import ssl
from datetime import datetime
from collections import deque
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import StandardScaler
import warnings
import base64
warnings.filterwarnings('ignore')

# ==========================================
# ⚙️ CONFIGURACIÓN MQTT
# ==========================================
BROKER = "ab78981ad7984d8c9f31e0e77a3b3962.s1.eu.hivemq.cloud"
PORT = 8883
USER = "jore-223010198"
PASS = "2223010198$Jore"

# Tópicos
TOPIC_SENSORES = "bosque/sensores"
TOPIC_ALERTAS = "seguridad/alertas"
TOPIC_MONITOR = "seguridad/monitor"
TOPIC_COMANDOS = "seguridad/comandos"

TIEMPO_LIMITE_DESCONEXION = 6

# ==========================================
# 🤖 MODELO DE IA - DETECCIÓN DE ANOMALÍAS
# ==========================================
class DetectorAnomalias:
    """Detector de anomalías usando Isolation Forest"""
    def __init__(self, ventana_entrenamiento=50):
        self.modelo = IsolationForest(
            contamination=0.1,
            random_state=42,
            n_estimators=100
        )
        self.scaler = StandardScaler()
        self.historial = deque(maxlen=ventana_entrenamiento)
        self.entrenado = False
        self.min_muestras = 20
    
    def agregar_muestra(self, temp, hum, gas):
        """Agrega una muestra al historial"""
        self.historial.append([temp, hum, gas])
        
        if len(self.historial) >= self.min_muestras and not self.entrenado:
            self._entrenar()
    
    def _entrenar(self):
        """Entrena el modelo con los datos acumulados"""
        datos = np.array(self.historial)
        datos_escalados = self.scaler.fit_transform(datos)
        self.modelo.fit(datos_escalados)
        self.entrenado = True
    
    def predecir(self, temp, hum, gas):
        """Predice si los datos son anómalos"""
        if not self.entrenado:
            return {
                "es_anomalia": False,
                "confianza": 0,
                "estado": "ENTRENANDO",
                "mensaje": f"Recolectando datos ({len(self.historial)}/{self.min_muestras})"
            }
        
        muestra = np.array([[temp, hum, gas]])
        muestra_escalada = self.scaler.transform(muestra)
        
        prediccion = self.modelo.predict(muestra_escalada)[0]
        score = self.modelo.decision_function(muestra_escalada)[0]
        
        confianza = min(100, max(0, int((1 - score) * 50 + 50)))
        es_anomalia = prediccion == -1
        
        return {
            "es_anomalia": es_anomalia,
            "confianza": confianza,
            "score": round(score, 3),
            "estado": "ALERTA" if es_anomalia else "NORMAL",
            "mensaje": "⚠️ Patrón inusual detectado" if es_anomalia else "✅ Valores normales"
        }
    
    def get_estadisticas(self):
        """Retorna estadísticas del modelo"""
        if len(self.historial) == 0:
            return None
        datos = np.array(self.historial)
        return {
            "muestras": len(self.historial),
            "temp_media": round(np.mean(datos[:, 0]), 1),
            "temp_std": round(np.std(datos[:, 0]), 2),
            "hum_media": round(np.mean(datos[:, 1]), 1),
            "hum_std": round(np.std(datos[:, 1]), 2),
            "gas_media": round(np.mean(datos[:, 2]), 1),
            "gas_std": round(np.std(datos[:, 2]), 2),
        }

# ==========================================
# 🧠 ANÁLISIS DE RIESGO MEJORADO
# ==========================================
def analizar_riesgo_avanzado(temp, gas_mq2, hum, distancia, prediccion_ia, movimiento_detectado):
    """Análisis de riesgo combinando reglas + IA + proximidad + gas MQ-2"""
    score = 0
    factores = []
    
    # Reglas de temperatura
    if temp > 45:
        score += 40
        factores.append("🔥 Temperatura crítica")
    elif temp > 35:
        score += 20
        factores.append("⚠️ Temperatura elevada")
    
    # NUEVO: Detección de gas MQ-2 (más sensible que el análogo)
    if gas_mq2 == 0:  # MQ-2 digital: 0 = gas detectado
        score += 45  # Máxima prioridad
        factores.append("🔥 GAS/HUMO DETECTADO (MQ-2)")
    
    # Humedad baja (riesgo de incendio)
    if hum < 20:
        score += 15
        factores.append("💧 Humedad muy baja")
    elif hum < 35:
        score += 5
        factores.append("💧 Humedad baja")
    
    # Bonus por detección de IA
    if prediccion_ia["es_anomalia"]:
        score += 20
        factores.append("🤖 IA detectó anomalía")
    
    # Detección de movimiento (cambio de umbral de audio)
    mensaje_extra = ""
    if movimiento_detectado:
        score += 10
        factores.append("⚡ Movimiento significativo detectado")
        mensaje_extra = " | ⚡ UMBRAL AUDIO AUMENTADO"
    
    # Detección de proximidad cercana
    if distancia > 0 and distancia < 50:
        factores.append(f"🚶 Objeto cercano: {distancia}cm")
        mensaje_extra += f" | 🚶 PROXIMIDAD {distancia}cm"
    
    # Determinar nivel de alerta
    if score >= 60:
        return {
            "nivel": "CRÍTICO",
            "color": "inverse",
            "icono": "🔥",
            "mensaje": f"¡ALERTA DE INCENDIO!{mensaje_extra}",
            "score": score,
            "factores": factores
        }
    elif score >= 30:
        return {
            "nivel": "ADVERTENCIA",
            "color": "off",
            "icono": "⚠️",
            "mensaje": f"Condiciones Peligrosas{mensaje_extra}",
            "score": score,
            "factores": factores
        }
    else:
        return {
            "nivel": "NORMAL",
            "color": "normal",
            "icono": "✅",
            "mensaje": f"Sistema Estable{mensaje_extra}",
            "score": score,
            "factores": factores
        }

# ==========================================
# 🖥️ CONFIGURACIÓN DE PÁGINA
# ==========================================
st.set_page_config(
    page_title="🌲 Monitor Forestal IA",
    page_icon="🌲",
    layout="wide",
    initial_sidebar_state="expanded"
)

# CSS Personalizado
st.markdown("""
<style>
    .main-header {
        font-size: 2.5rem;
        font-weight: 700;
        background: linear-gradient(90deg, #1e5631 0%, #2e7d32 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        text-align: center;
        padding: 1rem 0;
    }
    .audio-section {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        padding: 1.5rem;
        border-radius: 15px;
        color: white;
        margin: 1rem 0;
    }
    .alert-card {
        background: #ff5252;
        color: white;
        padding: 1rem;
        border-radius: 10px;
        margin: 0.5rem 0;
    }
    div[data-testid="stMetricValue"] { font-size: 2rem; }
</style>
""", unsafe_allow_html=True)

# ==========================================
# 🎨 INTERFAZ
# ==========================================
st.markdown('<h1 class="main-header">🌲 Monitor Central de Seguridad Forestal</h1>', unsafe_allow_html=True)
st.markdown('<p style="text-align:center; color:#666;">Sistema Integrado: Sensores Ambientales + Detección de Disparos con IA</p>', unsafe_allow_html=True)

# Estado de sesión para audio
if 'alertas_disparo' not in st.session_state:
    st.session_state.alertas_disparo = []
if 'ultimo_audio_monitor' not in st.session_state:
    st.session_state.ultimo_audio_monitor = None
if 'escuchando' not in st.session_state:
    st.session_state.escuchando = False

# Sidebar
with st.sidebar:
    st.markdown("### ⚙️ Configuración")
    st.markdown(f"**Broker:** `{BROKER[:20]}...`")
    st.markdown(f"**Topics:**")
    st.markdown(f"- Sensores: `{TOPIC_SENSORES}`")
    st.markdown(f"- Alertas: `{TOPIC_ALERTAS}`")
    st.markdown(f"- Monitor: `{TOPIC_MONITOR}`")
    st.markdown("---")
    st.markdown("### 🤖 Modelo IA")
    st.markdown("**Algoritmo:** Isolation Forest")
    st.markdown("**Sensores:** DHT11 + MQ-2 + Ultrasonido")
    st.markdown("**Audio IA:** YAMNet (Detección Disparos)")
    st.markdown("---")
    st.markdown("### 🎤 Control de Audio")
    
    # Toggle para activar/desactivar micrófono
    activar_mic = st.toggle(
        "🔴 Transmisión de Audio", 
        value=st.session_state.escuchando,
        help="Activa el streaming de audio en vivo"
    )
    
    if activar_mic != st.session_state.escuchando:
        st.session_state.escuchando = activar_mic

st.markdown("---")

# Contenedores principales
col_estado, col_dispositivo = st.columns([1, 2])
estado_rpi = col_estado.empty()
info_dispositivo = col_dispositivo.empty()

st.markdown("---")

# KPIs principales (6 columnas: añadimos MQ-2 y Umbral Audio)
st.markdown("### 📊 Métricas en Tiempo Real")
col1, col2, col3, col4, col5, col6 = st.columns(6)
kpi_temp = col1.empty()
kpi_hum = col2.empty()
kpi_gas_mq2 = col3.empty()  # NUEVO: MQ-2
kpi_dist = col4.empty()
kpi_umbral = col5.empty()   # NUEVO: Umbral audio
kpi_riesgo = col6.empty()

# Banner de alertas
st.markdown("### 📢 Estado del Sistema")
col_alert, col_ia = st.columns([2, 1])
alert_banner = col_alert.empty()
ia_status = col_ia.empty()

st.markdown("---")

# NUEVA SECCIÓN: Audio en Vivo y Alertas de Disparos
st.markdown("### 🎤 Sistema de Audio y Detección de Disparos")
col_audio_live, col_audio_alertas = st.columns([1, 1])

audio_live_container = col_audio_live.empty()
audio_alertas_container = col_audio_alertas.empty()

st.markdown("---")

# Sección de Hardware y Sensores
st.markdown("### 🛠️ Hardware y Sensores")
col_hw, col_sens, col_stats = st.columns(3)

info_hardware = col_hw.empty()
tabla_sensores = col_sens.empty()
stats_ia = col_stats.empty()

# Historial de datos
st.markdown("---")
st.markdown("### 📈 Análisis de IA")
col_factores, col_historial = st.columns([1, 2])
factores_riesgo = col_factores.empty()
grafico_historial = col_historial.empty()

# ==========================================
# 📌 CONEXIÓN MQTT
# ==========================================
@st.cache_resource
def obtener_recursos():
    memoria = {
        "ultimo_dato": None,
        "ultima_recepcion": 0,
        "historial_temp": deque(maxlen=100),
        "historial_hum": deque(maxlen=100),
        "historial_gas_mq2": deque(maxlen=100),
        "historial_dist": deque(maxlen=100),
        "timestamps": deque(maxlen=100)
    }
    
    detector_ia = DetectorAnomalias(ventana_entrenamiento=50)
    
    # Cliente para sensores
    def on_message_sensores(client, userdata, msg):
        try:
            payload = json.loads(msg.payload.decode())
            memoria["ultimo_dato"] = payload
            memoria["ultima_recepcion"] = time.time()
            
            t = payload.get('temp', 0)
            h = payload.get('hum', 0)
            g = payload.get('gas_mq2', 0)
            d = payload.get('distancia', 0)
            
            memoria["historial_temp"].append(t)
            memoria["historial_hum"].append(h)
            memoria["historial_gas_mq2"].append(g)
            memoria["historial_dist"].append(d)
            memoria["timestamps"].append(datetime.now())
            
            detector_ia.agregar_muestra(t, h, g)
        except:
            pass
    
    # Cliente MQTT principal (sensores)
    client_id = f"Dashboard_{datetime.now().strftime('%S%f')}"
    try:
        client_sensores = mqtt.Client(CallbackAPIVersion.VERSION2, client_id)
    except:
        client_sensores = mqtt.Client(client_id)
    
    client_sensores.username_pw_set(USER, PASS)
    client_sensores.tls_set(cert_reqs=ssl.CERT_NONE)
    client_sensores.on_message = on_message_sensores
    
    try:
        client_sensores.connect(BROKER, PORT)
        client_sensores.subscribe(TOPIC_SENSORES)
        client_sensores.loop_start()
    except:
        pass
    
    # Cliente para audio (con buzón de mensajes)
    client_audio = mqtt.Client(CallbackAPIVersion.VERSION2, f"Dashboard_Audio_{datetime.now().strftime('%S%f')}")
    client_audio.username_pw_set(USER, PASS)
    
    context = ssl.create_default_context()
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE
    client_audio.tls_set_context(context)
    
    # Buzón de mensajes de audio
    client_audio.buzon_mensajes = []
    
    def on_message_audio(c, userdata, msg):
        try:
            payload = json.loads(msg.payload.decode())
            c.buzon_mensajes.append((msg.topic, payload))
        except:
            pass
    
    client_audio.on_message = on_message_audio
    
    try:
        client_audio.connect(BROKER, PORT, 60)
        client_audio.subscribe([(TOPIC_ALERTAS, 0), (TOPIC_MONITOR, 0)])
        client_audio.loop_start()
    except Exception as e:
        print(f"Error conexión audio: {e}")
    
    return client_sensores, client_audio, memoria, detector_ia

client_sensores, client_audio, memoria, detector_ia = obtener_recursos()

# ==========================================
# 🔄 PROCESAR BUZÓN DE AUDIO
# ==========================================
if client_audio and hasattr(client_audio, 'buzon_mensajes'):
    while client_audio.buzon_mensajes:
        tema, datos = client_audio.buzon_mensajes.pop(0)
        
        if tema == TOPIC_ALERTAS:
            st.session_state.alertas_disparo.insert(0, datos)
            st.toast("🚨 ¡DISPARO DETECTADO!", icon="🔥")
        
        elif tema == TOPIC_MONITOR:
            st.session_state.ultimo_audio_monitor = datos

# Publicar comando de audio según el toggle
if st.session_state.escuchando:
    client_audio.publish(TOPIC_COMANDOS, "ON")
else:
    client_audio.publish(TOPIC_COMANDOS, "OFF")

# ==========================================
# 🔄 BUCLE PRINCIPAL
# ==========================================
data = memoria["ultimo_dato"]
ahora = time.time()
ultima_vez = memoria["ultima_recepcion"]
segundos_atras = ahora - ultima_vez

# === ONLINE ===
if data and segundos_atras < TIEMPO_LIMITE_DESCONEXION:
    t = data.get('temp', 0)
    h = data.get('hum', 0)
    g_mq2 = data.get('gas_mq2', 1)  # MQ-2: 1=limpio, 0=gas detectado
    d = data.get('distancia', 0)
    movimiento = data.get('movimiento_detectado', False)
    umbral_audio_actual = data.get('umbral_audio_actual', 0.25)
    hw = data.get('hardware', {})
    sensores = data.get('estado_sensores', {})
    filtro_info = data.get('filtro', {})
    datos_raw = data.get('datos_raw', {})

    # Predicción IA
    prediccion = detector_ia.predecir(t, h, g_mq2)
    
    # Análisis de riesgo combinado
    riesgo = analizar_riesgo_avanzado(t, g_mq2, h, d, prediccion, movimiento)

    # Estado conexión
    estado_rpi.success(f"🟢 **ONLINE** | Última lectura: hace {int(segundos_atras)}s")
    
    # Info dispositivo
    with info_dispositivo.container():
        c1, c2, c3 = st.columns(3)
        c1.markdown(f"**💻 Dispositivo:** {hw.get('modelo_rpi', 'N/A')}")
        c2.markdown(f"**🌡️ CPU:** {hw.get('cpu_temp', 'N/A')}°C")
        c3.markdown(f"**🐍 Python:** {hw.get('python_version', 'N/A')}")

    # KPIs (6 columnas)
    kpi_temp.metric(
        "🌡️ Temperatura",
        f"{t} °C",
        f"Raw: {datos_raw.get('temp', t)}°C",
        delta_color="inverse" if t > 35 else "normal"
    )
    kpi_hum.metric(
        "💧 Humedad",
        f"{h} %",
        f"Raw: {datos_raw.get('hum', h)}%"
    )
    
    # NUEVO: KPI para MQ-2
    estado_mq2 = "🔥 GAS!" if g_mq2 == 0 else "✅ Limpio"
    kpi_gas_mq2.metric(
        "🔥 MQ-2 (Gas)",
        estado_mq2,
        "Digital",
        delta_color="inverse" if g_mq2 == 0 else "normal"
    )
    
    kpi_dist.metric(
        "📏 Proximidad",
        f"{d} cm",
        "HC-SR04",
        delta_color="inverse" if d > 0 and d < 50 else "normal"
    )
    
    # NUEVO: KPI para umbral de audio
    kpi_umbral.metric(
        "🎚️ Umbral Audio",
        f"{umbral_audio_actual:.2f}",
        "INMP441",
        delta_color="inverse" if umbral_audio_actual <= 0.25 else "INMP441"
    )
    
    kpi_riesgo.metric(
        "⚡ Riesgo",
        f"{riesgo['score']}%",
        riesgo['nivel'],
        delta_color=riesgo['color']
    )

    # Alertas
    if riesgo['nivel'] == "CRÍTICO":
        alert_banner.error(f"## {riesgo['icono']} {riesgo['mensaje']}")
    elif riesgo['nivel'] == "ADVERTENCIA":
        alert_banner.warning(f"## {riesgo['icono']} {riesgo['mensaje']}")
    else:
        alert_banner.success(f"## {riesgo['icono']} {riesgo['mensaje']}")

    # Estado IA
    with ia_status.container():
        st.markdown("**🤖 Análisis IA**")
        if prediccion['estado'] == "ENTRENANDO":
            st.info(prediccion['mensaje'])
        elif prediccion['es_anomalia']:
            st.error(f"⚠️ ANOMALÍA (conf: {prediccion['confianza']}%)")
        else:
            st.success(f"✅ Normal (conf: {prediccion['confianza']}%)")

    # === SECCIÓN DE AUDIO ===
    # Audio en Vivo
    with audio_live_container.container():
        st.markdown("**🎧 Audio en Vivo**")
        if st.session_state.escuchando:
            if st.session_state.ultimo_audio_monitor:
                datos_audio = st.session_state.ultimo_audio_monitor
                hora = datetime.fromtimestamp(datos_audio['timestamp']).strftime('%H:%M:%S')
                st.info(f"📡 Transmitiendo - {hora}")
                audio_bytes = base64.b64decode(datos_audio['audio'])
                st.audio(audio_bytes, format='audio/wav', autoplay=True)
            else:
                st.warning("⏳ Sintonizando...")
        else:
            st.write("🔇 Micrófono desactivado. Actívalo desde el panel lateral.")

    # Alertas de Disparos
    with audio_alertas_container.container():
        st.markdown("**🚨 Alertas de Disparos**")
        if st.session_state.alertas_disparo:
            ultima_alerta = st.session_state.alertas_disparo[0]
            ts = datetime.fromtimestamp(ultima_alerta['timestamp']).strftime('%H:%M:%S')
            
            st.error(f"🔫 DISPARO DETECTADO a las {ts}")
            st.write(f"**Confianza:** {ultima_alerta['probabilidad']*100:.1f}%")
            
            audio_disparo = base64.b64decode(ultima_alerta['audio'])
            st.audio(audio_disparo, format='audio/wav')
            
            if len(st.session_state.alertas_disparo) > 1:
                st.caption(f"📋 {len(st.session_state.alertas_disparo)} alertas totales")
        else:
            st.success("✅ Sin alertas de disparos")

    # Hardware info
    with info_hardware.container():
        st.markdown("**📟 Información del Sistema**")
        st.markdown(f"- **Modelo:** {hw.get('modelo_rpi', 'N/A')}")
        st.markdown(f"- **Host:** {hw.get('hostname', 'N/A')}")
        st.markdown(f"- **Filtro:** Promedio de 3 muestras")
        st.markdown(f"- **Umbral Dinámico:** {umbral_audio_actual:.2f}")

    # Tabla de sensores
    with tabla_sensores.container():
        st.markdown("**📡 Estado de Sensores**")
        df = pd.DataFrame({
            "Sensor": ["DHT11", "HC-SR04", "MQ-2", "INMP441"],
            "Tipo": ["Temp/Hum", "Distancia", "Gas/Humo", "Audio"],
            "Estado": [
                sensores.get('dht11', 'N/A'),
                sensores.get('ultrasonido', 'N/A'),
                "ONLINE" if g_mq2 is not None else "OFFLINE",
                "ONLINE" if st.session_state.escuchando else "STANDBY"
            ]
        })
        st.dataframe(df, hide_index=True, use_container_width=True)

    # Estadísticas IA
    stats = detector_ia.get_estadisticas()
    with stats_ia.container():
        st.markdown("**📊 Estadísticas del Modelo**")
        if stats:
            st.markdown(f"- **Muestras:** {stats['muestras']}")
            st.markdown(f"- **Temp media:** {stats['temp_media']}°C ±{stats['temp_std']}")
            st.markdown(f"- **Hum media:** {stats['hum_media']}% ±{stats['hum_std']}")
        else:
            st.info("Recolectando datos...")

    # Factores de riesgo
    with factores_riesgo.container():
        st.markdown("**🎯 Factores de Riesgo Detectados**")
        if riesgo['factores']:
            for f in riesgo['factores']:
                st.markdown(f"- {f}")
        else:
            st.markdown("- Ninguno detectado ✅")

    # Gráfico historial
    with grafico_historial.container():
        if len(memoria["historial_temp"]) > 5:
            df_hist = pd.DataFrame({
                "Temperatura": list(memoria["historial_temp"]),
                "Humedad": list(memoria["historial_hum"]),
                "Gas MQ-2": list(memoria["historial_gas_mq2"]),
                "Distancia": list(memoria["historial_dist"])
            })
            st.line_chart(df_hist, height=200)

# === OFFLINE ===
elif data and segundos_atras >= TIEMPO_LIMITE_DESCONEXION:
    estado_rpi.error(f"🔴 **OFFLINE** | Perdido hace {int(segundos_atras)}s")
    info_dispositivo.warning("⚠️ Raspberry Pi no responde")
    
    kpi_temp.metric("🌡️ Temperatura", "--", "Sin señal")
    kpi_hum.metric("💧 Humedad", "--", "Sin señal")
    kpi_gas_mq2.metric("🔥 MQ-2", "--", "Sin señal")
    kpi_dist.metric("📏 Proximidad", "--", "Sin señal")
    kpi_umbral.metric("🎚️ Umbral", "--", "Sin señal")
    kpi_riesgo.metric("⚡ Riesgo", "--", "Sin datos")
    
    alert_banner.error("## 🔌 SISTEMA DESCONECTADO")
    ia_status.warning("IA pausada")
    
    audio_live_container.error("🔇 Audio desconectado")
    audio_alertas_container.warning("⚠️ Sin conexión con Raspberry Pi")

# === ESPERANDO ===
else:
    estado_rpi.info("⏳ Buscando dispositivo...")
    alert_banner.info("⏳ Esperando primera conexión con Raspberry Pi...")

time.sleep(1)

st.rerun()





