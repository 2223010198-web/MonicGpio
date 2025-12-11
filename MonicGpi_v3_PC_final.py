# -*- coding: utf-8 -*-
"""
🌲 DASHBOARD FORESTAL INTEGRADO (DISEÑO MEJORADO & AUDIO INDEPENDIENTE)
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
# ⚙️ CONFIGURACIÓN DE PÁGINA
# ==========================================
st.set_page_config(
    page_title="Monitor Forestal Pro",
    page_icon="🌲",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ==========================================
# 🎨 ESTILOS CSS MEJORADOS
# ==========================================
st.markdown("""
<style>
    /* Cabecera Principal */
    .main-header {
        font-size: 2.8rem; font-weight: 800;
        background: linear-gradient(90deg, #0f9b0f 0%, #000000 100%);
        -webkit-background-clip: text; -webkit-text-fill-color: transparent;
        text-align: center; padding-bottom: 0.5rem;
    }
    .sub-header {
        text-align: center; color: #555; font-size: 1.1rem; margin-bottom: 2rem;
    }
    
    /* Tarjetas de Sensores */
    .sensor-card {
        background-color: #f8f9fa;
        border-radius: 10px;
        padding: 15px;
        border-left: 5px solid #ccc;
        box-shadow: 2px 2px 5px rgba(0,0,0,0.05);
        margin-bottom: 10px;
    }
    .sensor-online { border-left-color: #28a745 !important; }
    .sensor-offline { border-left-color: #dc3545 !important; }
    
    .sensor-title { font-weight: bold; font-size: 1.1rem; color: #333; }
    .sensor-model { font-size: 0.9rem; color: #666; font-style: italic; }
    .sensor-status { float: right; font-weight: bold; }
    .status-ok { color: #28a745; }
    .status-err { color: #dc3545; }

    /* Métricas */
    div[data-testid="stMetricValue"] { font-size: 2rem; font-weight: 700; }
</style>
""", unsafe_allow_html=True)

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
TOPIC_DISPOSITIVO = "bosque/dispositivo"

TIEMPO_LIMITE_DESCONEXION = 10 

# ==========================================
# 🧠 CLASE INTELIGENCIA ARTIFICIAL
# ==========================================
class DetectorAnomalias:
    def __init__(self, ventana_entrenamiento=50):
        self.modelo = IsolationForest(contamination=0.1, random_state=42, n_estimators=100)
        self.scaler = StandardScaler()
        self.historial = deque(maxlen=ventana_entrenamiento)
        self.entrenado = False
        self.min_muestras = 20
    
    def agregar_muestra(self, temp, hum, gas):
        self.historial.append([temp, hum, gas])
        if len(self.historial) >= self.min_muestras and not self.entrenado:
            try:
                datos = np.array(self.historial)
                self.modelo.fit(self.scaler.fit_transform(datos))
                self.entrenado = True
            except: pass
    
    def predecir(self, temp, hum, gas):
        if not self.entrenado:
            return {"es_anomalia": False, "confianza": 0, "mensaje": "Calibrando IA..."}
        try:
            muestra_escalada = self.scaler.transform([[temp, hum, gas]])
            pred = self.modelo.predict(muestra_escalada)[0]
            score = self.modelo.decision_function(muestra_escalada)[0]
            return {
                "es_anomalia": pred == -1,
                "confianza": min(100, max(0, int((1 - score) * 50 + 50))),
                "mensaje": "⚠️ ANOMALÍA DETECTADA" if pred == -1 else "✅ Patrones Normales"
            }
        except:
             return {"es_anomalia": False, "confianza": 0, "mensaje": "Error IA"}

# ==========================================
# 💾 GESTOR DE ESTADO COMPARTIDO
# ==========================================
class EstadoCompartido:
    """Memoria compartida para todos los usuarios"""
    def __init__(self):
        self.ultimo_dato = None
        self.ultima_recepcion = 0
        self.ultimo_audio_monitor = None
        self.info_dispositivo = {}
        
        # Historiales
        self.hist_temp = deque(maxlen=50)
        self.hist_hum = deque(maxlen=50)
        self.hist_gas = deque(maxlen=50)
        
        # Alertas
        self.alertas_disparo = deque(maxlen=5)
        
        # IA Compartida
        self.detector_ia = DetectorAnomalias()

# ==========================================
# 📡 CONEXIÓN MQTT (GLOBAL)
# ==========================================
@st.cache_resource
def iniciar_sistema_central():
    """Inicia MQTT una sola vez y lo comparte"""
    estado = EstadoCompartido()
    
    def on_message(client, userdata, msg):
        try:
            payload = json.loads(msg.payload.decode())
            topic = msg.topic
            
            if topic == TOPIC_SENSORES:
                estado.ultimo_dato = payload
                estado.ultima_recepcion = time.time()
                
                estado.hist_temp.append(payload.get('temp', 0))
                estado.hist_hum.append(payload.get('hum', 0))
                estado.hist_gas.append(payload.get('gas_mq2', 0))
                
                estado.detector_ia.agregar_muestra(
                    payload.get('temp', 0), 
                    payload.get('hum', 0), 
                    payload.get('gas_mq2', 0)
                )

            elif topic == TOPIC_ALERTAS:
                estado.alertas_disparo.appendleft(payload)
            
            elif topic == TOPIC_MONITOR:
                estado.ultimo_audio_monitor = payload
            
            elif topic == TOPIC_DISPOSITIVO:
                estado.info_dispositivo = payload

        except Exception as e:
            print(f"Error procesando mensaje: {e}")

    client_id = f"Dash_Master_{datetime.now().strftime('%H%M%S')}"
    client = mqtt.Client(CallbackAPIVersion.VERSION2, client_id)
    client.username_pw_set(USER, PASS)
    client.tls_set_context(ssl.create_default_context())
    client.on_message = on_message
    
    try:
        client.connect(BROKER, PORT, 60)
        client.subscribe([
            (TOPIC_SENSORES, 0),
            (TOPIC_ALERTAS, 2),
            (TOPIC_MONITOR, 0),
            (TOPIC_DISPOSITIVO, 0)
        ])
        client.loop_start()
    except Exception as e:
        st.error(f"Error Broker MQTT: {e}")

    return estado, client

estado_compartido, cliente_mqtt = iniciar_sistema_central()

# ==========================================
# 🧠 LÓGICA DE RIESGO
# ==========================================
def analizar_riesgo(temp, gas_mq2, hum, distancia, prediccion_ia, movimiento):
    score = 0
    factores = []
    
    # 1. Temperatura
    if temp > 45: score += 40; factores.append("🔥 Temperatura crítica")
    elif temp > 35: score += 20; factores.append("⚠️ Temperatura elevada")
    
    # 2. Gas (0 = Detectado)
    if gas_mq2 == 0: 
        score += 45
        factores.append("🔥 GAS/HUMO DETECTADO")
    
    # 3. Humedad
    if hum < 20: score += 15; factores.append("💧 Aire muy seco")
    
    # 4. IA
    if prediccion_ia["es_anomalia"]: 
        score += 20
        factores.append("🤖 Patrón anómalo (IA)")
    
    # 5. Movimiento
    mensaje_extra = ""
    if movimiento:
        score += 10
        factores.append("⚡ Movimiento detectado")
        mensaje_extra = " | ⚡ ALERTA MOVIMIENTO"
    
    # 6. Proximidad
    if 0 < distancia < 50:
        factores.append(f"🚶 Proximidad: {distancia}cm")
    
    # Evaluación Final
    if score >= 60:
        return {"nivel": "CRÍTICO", "color": "inverse", "icono": "🔥", "mensaje": f"¡PELIGRO!{mensaje_extra}", "score": score, "factores": factores}
    elif score >= 30:
        return {"nivel": "ADVERTENCIA", "color": "off", "icono": "⚠️", "mensaje": f"Precaución{mensaje_extra}", "score": score, "factores": factores}
    else:
        return {"nivel": "NORMAL", "color": "normal", "icono": "✅", "mensaje": f"Seguro{mensaje_extra}", "score": score, "factores": factores}

# ==========================================
# 🎨 FUNCIÓN AUXILIAR: TARJETA DE SENSOR
# ==========================================
def mostrar_tarjeta_sensor(nombre, modelo, estado_raw):
    """Genera una tarjeta visual HTML para el estado del sensor"""
    # Determinar estado
    conectado = False
    if isinstance(estado_raw, dict): # Formato nuevo
        conectado = estado_raw.get('conectado', False)
        # Si dice ONLINE en texto dentro del dict
        if not conectado and "ONLINE" in str(estado_raw): conectado = True
    else: # Formato simple (string)
        conectado = (str(estado_raw) == "ONLINE")

    # Clases CSS
    css_class = "sensor-online" if conectado else "sensor-offline"
    status_txt_class = "status-ok" if conectado else "status-err"
    status_label = "ONLINE" if conectado else "OFFLINE"
    icon = "🟢" if conectado else "🔴"

    html = f"""
    <div class="sensor-card {css_class}">
        <div class="sensor-title">{icon} {nombre}</div>
        <div class="sensor-model">Modelo: {modelo}</div>
        <div class="sensor-status {status_txt_class}">{status_label}</div>
    </div>
    """
    st.markdown(html, unsafe_allow_html=True)

# ==========================================
# 🎛️ SIDEBAR Y AUDIO (LÓGICA CORREGIDA)
# ==========================================
# Estado local para el toggle de audio (Solo afecta a este navegador)
if 'audio_local_activo' not in st.session_state:
    st.session_state.audio_local_activo = False

st.markdown('<h1 class="main-header">🌲 Monitor Forestal Pro</h1>', unsafe_allow_html=True)
st.markdown('<div class="sub-header">Centro de Comando: Sensores Ambientales + IA + Audio Táctico</div>', unsafe_allow_html=True)

with st.sidebar:
    st.markdown("### ⚙️ Panel de Control")
    st.info(f"📡 Broker: HiveMQ Cloud\n🟢 Conectado")
    
    st.markdown("---")
    st.markdown("### 🎧 Control de Audio")
    
    # 1. Toggle Local: Solo muestra/oculta el reproductor y asegura que la RPi transmita
    escuchar = st.toggle("🔈 Escuchar Audio en Vivo", value=st.session_state.audio_local_activo)
    
    if escuchar != st.session_state.audio_local_activo:
        st.session_state.audio_local_activo = escuchar
        if escuchar:
            # Si YO activo el audio, envío ON para asegurar que la RPi transmita.
            # No importa si ya estaba transmitiendo, aseguramos el flujo.
            cliente_mqtt.publish(TOPIC_COMANDOS, "ON")
            st.toast("Conectando audio...", icon="🎧")
        else:
            # Si YO desactivo, SOLO oculto mi reproductor.
            # NO envío "OFF" para no cortarle el audio a otros usuarios.
            st.toast("Audio silenciado localmente", icon="🔇")
            

# ==========================================
# 🔄 PROCESAMIENTO Y VISUALIZACIÓN
# ==========================================
data = estado_compartido.ultimo_dato
tiempo_transcurrido = time.time() - estado_compartido.ultima_recepcion

col_estado, col_hw = st.columns([1, 2])
estado_con = col_estado.empty()
info_hw = col_hw.empty()

st.markdown("---")

# 1. KPIs
col1, col2, col3, col4, col5, col6 = st.columns(6)
kpi_t, kpi_h, kpi_g = col1.empty(), col2.empty(), col3.empty()
kpi_d, kpi_u, kpi_r = col4.empty(), col5.empty(), col6.empty()

# 2. Tarjetas de Sensores (NUEVO DISEÑO)
st.markdown("### 📡 Estado de Dispositivos y Sensores")
col_s1, col_s2, col_s3, col_s4 = st.columns(4)
card_dht = col_s1.empty()
card_ultra = col_s2.empty()
card_mq2 = col_s3.empty()
card_mic = col_s4.empty()

st.markdown("---")

# 3. Audio y Alertas
col_audio, col_alertas = st.columns([1, 1])
with col_audio:
    st.markdown("### 🎧 Audio en Tiempo Real")
    cont_audio = st.empty()
with col_alertas:
    st.markdown("### 🚨 Última Alerta de Seguridad")
    cont_alertas = st.empty()

st.markdown("---")
col_graf, col_ia = st.columns([2, 1])
graficos = col_graf.empty()
info_ia = col_ia.empty()

# ==========================================
# 🖥️ RENDERIZADO
# ==========================================
if data and tiempo_transcurrido < TIEMPO_LIMITE_DESCONEXION:
    # --- Datos ---
    t = data.get('temp', 0)
    h = data.get('hum', 0)
    g = data.get('gas_mq2', 1)
    d = data.get('distancia', 0)
    mov = data.get('movimiento_detectado', False)
    umbral = data.get('umbral_audio_actual', 0.50)
    sensores = data.get('estado_sensores', {})
    hw = data.get('hardware', {})
    
    # --- IA y Riesgo ---
    prediccion = estado_compartido.detector_ia.predecir(t, h, g)
    riesgo = analizar_riesgo(t, g, h, d, prediccion, mov)
    
    # --- Header ---
    estado_con.success(f"🟢 **SISTEMA ONLINE** | Latencia: {int(tiempo_transcurrido*1000)}ms")
    info_hw.info(f"💻 **Nodo:** {hw.get('modelo_rpi', 'RPi')} | **CPU:** {hw.get('cpu_temp', 0)}°C")
    
    # --- KPIs ---
    kpi_t.metric("🌡️ Temp", f"{t}°C", delta_color="inverse" if t > 35 else "normal")
    kpi_h.metric("💧 Humedad", f"{h}%")
    kpi_g.metric("♨️ Gas", "DETECTADO" if g == 0 else "Normal", delta_color="inverse" if g == 0 else "normal")
    kpi_d.metric("📏 Distancia", f"{d}cm", delta_color="inverse" if 0 < d < 50 else "normal")
    
    lbl_umb = "🚨 ALERTA" if umbral <= 0.25 else "🛡️ VIGILANCIA"
    kpi_u.metric("🎚️ Umbral IA", f"{umbral:.2f}", lbl_umb, delta_color="inverse" if umbral <= 0.25 else "normal")
    kpi_r.metric("⚡ Riesgo", f"{riesgo['score']}", riesgo['nivel'], delta_color=riesgo['color'])
    
    # --- TARJETAS DE SENSORES (DISEÑO MEJORADO) ---
    with card_dht.container(): mostrar_tarjeta_sensor("Clima", "DHT11 Digital", sensores.get('dht11', 'OFFLINE'))
    with card_ultra.container(): mostrar_tarjeta_sensor("Proximidad", "HC-SR04", sensores.get('ultrasonido', 'OFFLINE'))
    with card_mq2.container(): mostrar_tarjeta_sensor("Gas/Humo", "MQ-2", sensores.get('mq2', 'OFFLINE'))
    with card_mic.container(): mostrar_tarjeta_sensor("Micrófono", "INMP441 I2S", sensores.get('mic_inmp441', 'OFFLINE'))

    # --- AUDIO (Lógica corregida) ---
    with cont_audio.container():
        if st.session_state.audio_local_activo:
            audio_data = estado_compartido.ultimo_audio_monitor
            if audio_data:
                ts = datetime.fromtimestamp(audio_data['timestamp']).strftime('%H:%M:%S')
                st.caption(f"📡 Recibiendo flujo - {ts}")
                # Usar key única basada en timestamp para forzar recarga
                st.audio(base64.b64decode(audio_data['audio']), format='audio/wav', autoplay=True)
            else:
                st.warning("⏳ Esperando paquetes de audio...")
        else:
            st.info("🔇 Audio desactivado (Actívalo en el menú lateral)")

    # --- ALERTAS ---
    with cont_alertas.container():
        if estado_compartido.alertas_disparo:
            last = estado_compartido.alertas_disparo[0]
            ts_alert = datetime.fromtimestamp(last['timestamp']).strftime('%H:%M:%S')
            st.error(f"🔫 DISPARO DETECTADO a las {ts_alert}")
            st.progress(last['probabilidad'], text=f"Confianza IA: {last['probabilidad']*100:.1f}%")
            st.audio(base64.b64decode(last['audio']), format='audio/wav')
        else:
            st.success("✅ Zona segura: Sin disparos recientes")

    # --- GRÁFICOS E IA ---
    with graficos.container():
        if len(estado_compartido.hist_temp) > 0:
            df = pd.DataFrame({
                "Temp (°C)": list(estado_compartido.hist_temp),
                "Humedad (%)": list(estado_compartido.hist_hum)
            })
            st.area_chart(df, height=200, color=["#ffaa00", "#00aaff"])
    
    with info_ia.container():
        st.markdown("#### 🤖 Diagnóstico IA")
        if prediccion['es_anomalia']:
            st.error(f"{prediccion['mensaje']} ({prediccion['confianza']}%)")
        else:
            st.success(f"{prediccion['mensaje']} ({prediccion['confianza']}%)")
            
else:
    # OFFLINE
    estado_con.error("🔴 **SISTEMA OFFLINE**")
    st.warning("⚠️ No se reciben datos de la Raspberry Pi. Verifique conexión a Internet y alimentación.")

# Refresco
time.sleep(1)
st.rerun()

