# -*- coding: utf-8 -*-
"""
🌲 DASHBOARD FORESTAL INTEGRADO (MULTI-USUARIO & V6 COMPATIBLE)
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
    page_title="🌲 Monitor Forestal IA",
    page_icon="🌲",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ==========================================
# ⚙️ CONFIGURACIÓN MQTT
# ==========================================
BROKER = "ab78981ad7984d8c9f31e0e77a3b3962.s1.eu.hivemq.cloud"
PORT = 8883
USER = "jore-223010198"
PASS = "2223010198$Jore"

# Tópicos (Coincidentes con RPi v6)
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
            except:
                pass # Evitar crash si los datos son constantes
    
    def predecir(self, temp, hum, gas):
        if not self.entrenado:
            return {"es_anomalia": False, "confianza": 0, "estado": "ENTRENANDO", 
                    "mensaje": f"Recolectando datos ({len(self.historial)}/{self.min_muestras})"}
        try:
            muestra_escalada = self.scaler.transform([[temp, hum, gas]])
            pred = self.modelo.predict(muestra_escalada)[0]
            score = self.modelo.decision_function(muestra_escalada)[0]
            return {
                "es_anomalia": pred == -1,
                "confianza": min(100, max(0, int((1 - score) * 50 + 50))),
                "estado": "ALERTA" if pred == -1 else "NORMAL",
                "mensaje": "⚠️ Patrón inusual" if pred == -1 else "✅ Valores normales"
            }
        except:
             return {"es_anomalia": False, "confianza": 0, "estado": "ERROR", "mensaje": "Error IA"}
    
    def get_estadisticas(self):
        if not self.historial: return None
        d = np.array(self.historial)
        return {
            "muestras": len(d),
            "temp_media": round(np.mean(d[:, 0]), 1), "temp_std": round(np.std(d[:, 0]), 2),
            "hum_media": round(np.mean(d[:, 1]), 1), "hum_std": round(np.std(d[:, 1]), 2)
        }

# ==========================================
# 💾 GESTOR DE ESTADO COMPARTIDO (SINGLETON)
# ==========================================
class EstadoCompartido:
    """Memoria compartida para todos los usuarios conectados"""
    def __init__(self):
        self.ultimo_dato = None
        self.ultima_recepcion = 0
        self.ultimo_audio_monitor = None
        self.info_dispositivo = {}
        
        # Historiales
        self.hist_temp = deque(maxlen=50)
        self.hist_hum = deque(maxlen=50)
        self.hist_gas = deque(maxlen=50)
        self.hist_dist = deque(maxlen=50)
        
        # Alertas
        self.alertas_disparo = deque(maxlen=5)
        
        # IA Compartida
        self.detector_ia = DetectorAnomalias()

# ==========================================
# 📡 CONEXIÓN MQTT (GLOBAL CACHED)
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
                estado.hist_dist.append(payload.get('distancia', 0))
                
                estado.detector_ia.agregar_muestra(
                    payload.get('temp', 0), 
                    payload.get('hum', 0), 
                    payload.get('gas_mq2', 0)
                )

            elif topic == TOPIC_ALERTAS:
                estado.alertas_disparo.appendleft(payload) # Insertar al principio
            
            elif topic == TOPIC_MONITOR:
                estado.ultimo_audio_monitor = payload
            
            elif topic == TOPIC_DISPOSITIVO:
                estado.info_dispositivo = payload

        except Exception as e:
            print(f"Error procesando mensaje: {e}")

    # Cliente MQTT
    client_id = f"Dashboard_Master_{datetime.now().strftime('%H%M%S')}"
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
        st.error(f"Error conectando al Broker MQTT: {e}")

    return estado, client

# Obtener instancia compartida
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
    
    # 2. Gas (0 = Detectado en digital)
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
# 🎨 DISEÑO E INTERFAZ
# ==========================================
st.markdown("""
<style>
    .main-header {
        font-size: 2.5rem; font-weight: 700;
        background: linear-gradient(90deg, #1e5631 0%, #2e7d32 100%);
        -webkit-background-clip: text; -webkit-text-fill-color: transparent;
        text-align: center; padding: 1rem 0;
    }
    div[data-testid="stMetricValue"] { font-size: 1.8rem; }
    .audio-card { background-color: #f0f2f6; padding: 15px; border-radius: 10px; }
</style>
""", unsafe_allow_html=True)

st.markdown('<h1 class="main-header">🌲 Monitor Central de Seguridad Forestal</h1>', unsafe_allow_html=True)
st.markdown('<p style="text-align:center; color:#666;">Sistema Integrado: Sensores Ambientales + Detección de Disparos con IA</p>', unsafe_allow_html=True)

# Toggle local para controlar el comando
if 'mic_activo' not in st.session_state:
    st.session_state.mic_activo = False

# ==========================================
# 🎛️ SIDEBAR
# ==========================================
with st.sidebar:
    st.markdown("### ⚙️ Panel de Control")
    st.info(f"📡 Broker: HiveMQ Cloud\n🟢 Estado: Conectado")
    
    st.markdown("---")
    st.markdown("### 🎤 Audio Remoto")
    
    # Control de Audio
    toggle_mic = st.toggle("🔴 Activar Escucha", value=st.session_state.mic_activo)
    
    if toggle_mic != st.session_state.mic_activo:
        st.session_state.mic_activo = toggle_mic
        cmd = "ON" if toggle_mic else "OFF"
        cliente_mqtt.publish(TOPIC_COMANDOS, cmd)
        if toggle_mic:
            st.toast("🎤 Solicitando audio...", icon="📡")
        else:
            st.toast("🔇 Audio desactivado", icon="🛑")
            
    st.caption("Al activar, todos los usuarios conectados podrán escuchar el audio.")

# ==========================================
# 🔄 PROCESAMIENTO
# ==========================================
data = estado_compartido.ultimo_dato
tiempo_transcurrido = time.time() - estado_compartido.ultima_recepcion

# Layout
col_estado, col_dispositivo = st.columns([1, 2])
estado_con = col_estado.empty()
info_hw = col_dispositivo.empty()

st.markdown("---")

col1, col2, col3, col4, col5, col6 = st.columns(6)
kpi_t, kpi_h, kpi_g = col1.empty(), col2.empty(), col3.empty()
kpi_d, kpi_u, kpi_r = col4.empty(), col5.empty(), col6.empty()

alert_banner = st.empty()
col_audio_live, col_audio_alertas = st.columns([1, 1])

st.markdown("---")
col_extra1, col_extra2 = st.columns([1, 2])
tabla_sensores = col_extra1.empty()
graficos = col_extra2.empty()

# ==========================================
# 🖥️ VISUALIZACIÓN
# ==========================================
if data and tiempo_transcurrido < TIEMPO_LIMITE_DESCONEXION:
    # 1. Parsear datos (Compatible v6)
    t = data.get('temp', 0)
    h = data.get('hum', 0)
    g = data.get('gas_mq2', 1)
    d = data.get('distancia', 0)
    mov = data.get('movimiento_detectado', False)
    umbral = data.get('umbral_audio_actual', 0.50)
    
    sensores_dict = data.get('estado_sensores', {})
    hw_info = data.get('hardware', {})
    
    # 2. Análisis
    prediccion = estado_compartido.detector_ia.predecir(t, h, g)
    riesgo = analizar_riesgo(t, g, h, d, prediccion, mov)
    
    # 3. Estado
    estado_con.success(f"🟢 **ONLINE** | Ping: {int(tiempo_transcurrido)}s")
    
    # 4. Info Hardware
    with info_hw.container():
        c1, c2, c3 = st.columns(3)
        c1.markdown(f"**💻 Modelo:** {hw_info.get('modelo_rpi', 'RPi')}")
        c2.markdown(f"**🌡️ CPU:** {hw_info.get('cpu_temp', 0)}°C")
        c3.markdown(f"**📡 Host:** {hw_info.get('hostname', 'Forestal')}")
    
    # 5. KPIs
    kpi_t.metric("🌡️ Temp", f"{t}°C", delta_color="inverse" if t > 35 else "normal")
    kpi_h.metric("💧 Humedad", f"{h}%")
    
    gas_label = "🔥 GAS!" if g == 0 else "✅ Aire Puro"
    kpi_g.metric("♨️ Gas MQ-2", gas_label, delta_color="inverse" if g == 0 else "normal")
    
    kpi_d.metric("📏 Distancia", f"{d}cm", delta_color="inverse" if 0 < d < 50 else "normal")
    
    # Lógica de Color Umbral (0.25 = Rojo/Alerta, 0.50 = Verde/Normal)
    color_umbral = "inverse" if umbral <= 0.25 else "normal"
    label_umbral = "🚨 ALERTA" if umbral <= 0.25 else "🛡️ VIGILANCIA"
    kpi_u.metric("🎚️ Umbral IA", f"{umbral:.2f}", label_umbral, delta_color=color_umbral)
    
    kpi_r.metric("⚡ Riesgo", f"{riesgo['score']}%", riesgo['nivel'], delta_color=riesgo['color'])
    
    # 6. Alertas Banner
    if riesgo['nivel'] == "CRÍTICO":
        alert_banner.error(f"## {riesgo['icono']} {riesgo['mensaje']}")
    elif riesgo['nivel'] == "ADVERTENCIA":
        alert_banner.warning(f"## {riesgo['icono']} {riesgo['mensaje']}")
    else:
        alert_banner.success(f"## {riesgo['icono']} {riesgo['mensaje']}")
        
    # 7. Tabla Sensores (Mapeo v6)
    with tabla_sensores.container():
        st.markdown("#### 📡 Estado de Sensores")
        
        # v6 envía diccionarios dentro de estado_sensores o strings simples. Manejamos ambos.
        def get_status(key, name):
            if isinstance(sensores_dict, dict):
                val = sensores_dict.get(key, 'N/A')
                # Si es diccionario (v6 complejo)
                if isinstance(val, dict):
                    return "✅ ONLINE" if val.get('conectado', False) else "❌ ERROR"
                # Si es string (v6 simple)
                return val
            return "N/A"

        data_s = [
            {"Sensor": "DHT11 (Clima)", "Estado": get_status('DHT11', 'dht11')},
            {"Sensor": "HC-SR04 (Distancia)", "Estado": get_status('Ultrasonido', 'ultrasonido')},
            {"Sensor": "MQ-2 (Gas)", "Estado": get_status('Gas', 'mq2')},
            {"Sensor": "Micrófono (IA)", "Estado": get_status('Microfono', 'mic_inmp441')},
        ]
        st.dataframe(pd.DataFrame(data_s), hide_index=True, use_container_width=True)
        
        if prediccion['es_anomalia']:
            st.warning(f"🤖 IA: {prediccion['mensaje']}")
        else:
            st.success(f"🤖 IA: {prediccion['mensaje']}")

    # 8. Gráficos
    with graficos.container():
        if len(estado_compartido.hist_temp) > 0:
            df_hist = pd.DataFrame({
                "Temp": list(estado_compartido.hist_temp),
                "Hum": list(estado_compartido.hist_hum),
                "Gas": list(estado_compartido.hist_gas)
            })
            st.line_chart(df_hist, height=220)

else:
    # OFFLINE
    estado_con.error(f"🔴 **OFFLINE** | Conexión perdida hace {int(tiempo_transcurrido)}s")
    info_hw.warning("Esperando datos de Raspberry Pi...")
    alert_banner.info("⏳ Esperando conexión...")

# ==========================================
# 🎤 SECCIÓN DE AUDIO (SINCRONIZADA)
# ==========================================
with col_audio_live:
    st.markdown("#### 🎧 Audio en Vivo")
    if st.session_state.mic_activo:
        audio_data = estado_compartido.ultimo_audio_monitor
        if audio_data:
            ts = datetime.fromtimestamp(audio_data['timestamp']).strftime('%H:%M:%S')
            st.caption(f"📡 Recibido: {ts}")
            # Usamos key única para forzar recarga del reproductor
            st.audio(base64.b64decode(audio_data['audio']), format='audio/wav', autoplay=True)
        else:
            st.warning("⏳ Buffering...")
    else:
        st.info("🔇 Micrófono apagado")

with col_audio_alertas:
    st.markdown("#### 🚨 Última Alerta")
    if estado_compartido.alertas_disparo:
        last_alert = estado_compartido.alertas_disparo[0]
        ts_alert = datetime.fromtimestamp(last_alert['timestamp']).strftime('%H:%M:%S')
        
        st.error(f"🔫 DISPARO - {ts_alert}")
        st.metric("Confianza IA", f"{last_alert['probabilidad']*100:.1f}%")
        st.audio(base64.b64decode(last_alert['audio']), format='audio/wav')
    else:
        st.success("✅ Sin incidentes")

# Refresco automático (1s)
time.sleep(1)
st.rerun()
