# -*- coding: utf-8 -*-
"""
🌲 DASHBOARD FORESTAL INTEGRADO CON IA (MULTI-USUARIO)
Monitor Central: Sensores Ambientales + Detección de Disparos + Audio en Vivo
Compatible con Raspberry Pi v6 + HiveMQ
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

# Tópicos
TOPIC_SENSORES = "bosque/sensores"
TOPIC_ALERTAS = "seguridad/alertas"
TOPIC_MONITOR = "seguridad/monitor"
TOPIC_COMANDOS = "seguridad/comandos"
TOPIC_DISPOSITIVO = "bosque/dispositivo"

TIEMPO_LIMITE_DESCONEXION = 10 # Segundos para considerar offline

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
            datos = np.array(self.historial)
            self.modelo.fit(self.scaler.fit_transform(datos))
            self.entrenado = True
    
    def predecir(self, temp, hum, gas):
        if not self.entrenado:
            return {"es_anomalia": False, "confianza": 0, "estado": "ENTRENANDO", 
                    "mensaje": f"Recolectando datos ({len(self.historial)}/{self.min_muestras})"}
        
        muestra_escalada = self.scaler.transform([[temp, hum, gas]])
        pred = self.modelo.predict(muestra_escalada)[0]
        score = self.modelo.decision_function(muestra_escalada)[0]
        return {
            "es_anomalia": pred == -1,
            "confianza": min(100, max(0, int((1 - score) * 50 + 50))),
            "estado": "ALERTA" if pred == -1 else "NORMAL",
            "mensaje": "⚠️ Patrón inusual" if pred == -1 else "✅ Valores normales"
        }
    
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
    """Clase para almacenar datos compartidos entre todos los usuarios del dashboard"""
    def __init__(self):
        self.ultimo_dato = None
        self.ultima_recepcion = 0
        self.ultimo_audio_monitor = None
        self.info_dispositivo = {}
        
        # Historiales compartidos para gráficos
        self.hist_temp = deque(maxlen=50)
        self.hist_hum = deque(maxlen=50)
        self.hist_gas = deque(maxlen=50)
        self.hist_dist = deque(maxlen=50)
        
        # Alertas recientes (FIFO)
        self.alertas_disparo = deque(maxlen=5)
        
        # Instancia única del detector IA
        self.detector_ia = DetectorAnomalias()

# ==========================================
# 📡 CONEXIÓN MQTT (GLOBAL CACHED)
# ==========================================
@st.cache_resource
def iniciar_sistema_central():
    """Inicia MQTT y Estado Compartido UNA SOLA VEZ"""
    estado = EstadoCompartido()
    
    def on_message(client, userdata, msg):
        try:
            payload = json.loads(msg.payload.decode())
            topic = msg.topic
            
            if topic == TOPIC_SENSORES:
                estado.ultimo_dato = payload
                estado.ultima_recepcion = time.time()
                
                # Guardar en historiales
                estado.hist_temp.append(payload.get('temp', 0))
                estado.hist_hum.append(payload.get('hum', 0))
                estado.hist_gas.append(payload.get('gas_mq2', 0))
                estado.hist_dist.append(payload.get('distancia', 0))
                
                # Entrenar IA
                estado.detector_ia.agregar_muestra(
                    payload.get('temp', 0), 
                    payload.get('hum', 0), 
                    payload.get('gas_mq2', 0)
                )

            elif topic == TOPIC_ALERTAS:
                # Insertar al inicio (nueva alerta)
                estado.alertas_disparo.appendleft(payload)
            
            elif topic == TOPIC_MONITOR:
                estado.ultimo_audio_monitor = payload
            
            elif topic == TOPIC_DISPOSITIVO:
                estado.info_dispositivo = payload

        except Exception as e:
            print(f"Error procesando mensaje: {e}")

    # Configuración Cliente MQTT
    client_id = f"Dashboard_Master_{datetime.now().strftime('%H%M%S')}"
    client = mqtt.Client(CallbackAPIVersion.VERSION2, client_id)
    client.username_pw_set(USER, PASS)
    client.tls_set_context(ssl.create_default_context())
    client.on_message = on_message
    
    try:
        client.connect(BROKER, PORT, 60)
        # Suscribirse a todos los tópicos relevantes
        client.subscribe([
            (TOPIC_SENSORES, 0),
            (TOPIC_ALERTAS, 2),  # QoS 2 para alertas (importante)
            (TOPIC_MONITOR, 0),
            (TOPIC_DISPOSITIVO, 0)
        ])
        client.loop_start()
    except Exception as e:
        st.error(f"Error conectando al Broker MQTT: {e}")

    return estado, client

# Iniciar recursos (o recuperar caché)
estado_compartido, cliente_mqtt = iniciar_sistema_central()

# ==========================================
# 🧠 LÓGICA DE RIESGO
# ==========================================
def analizar_riesgo(temp, gas_mq2, hum, distancia, prediccion_ia, movimiento):
    score = 0
    factores = []
    
    if temp > 45: score += 40; factores.append("🔥 Temperatura crítica")
    elif temp > 35: score += 20; factores.append("⚠️ Temperatura elevada")
    
    # Gas MQ-2 (0 es detectado en digital)
    if gas_mq2 == 0: 
        score += 45
        factores.append("🔥 GAS/HUMO DETECTADO")
    
    if hum < 20: score += 15; factores.append("💧 Aire muy seco")
    
    if prediccion_ia["es_anomalia"]: 
        score += 20
        factores.append("🤖 Patrón anómalo (IA)")
    
    mensaje_extra = ""
    if movimiento:
        score += 10
        factores.append("⚡ Movimiento detectado")
        mensaje_extra = " | ⚡ ALERTA MOVIMIENTO"
    
    if 0 < distancia < 50:
        factores.append(f"🚶 Proximidad: {distancia}cm")
    
    if score >= 60:
        return {"nivel": "CRÍTICO", "color": "inverse", "icono": "🔥", "mensaje": f"¡PELIGRO!{mensaje_extra}", "score": score, "factores": factores}
    elif score >= 30:
        return {"nivel": "ADVERTENCIA", "color": "off", "icono": "⚠️", "mensaje": f"Precaución{mensaje_extra}", "score": score, "factores": factores}
    else:
        return {"nivel": "NORMAL", "color": "normal", "icono": "✅", "mensaje": f"Seguro{mensaje_extra}", "score": score, "factores": factores}

# ==========================================
# 🎨 INTERFAZ GRÁFICA (CSS)
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
</style>
""", unsafe_allow_html=True)

st.markdown('<h1 class="main-header">🌲 Monitor Central de Seguridad Forestal</h1>', unsafe_allow_html=True)

# Control de Sesión Local (Toggle Micrófono)
if 'escuchando' not in st.session_state:
    st.session_state.escuchando = False

# ==========================================
# 🎛️ SIDEBAR
# ==========================================
with st.sidebar:
    st.markdown("### ⚙️ Panel de Control")
    st.info(f"📡 Broker: HiveMQ Cloud\n🟢 Estado: Conectado")
    
    st.markdown("---")
    st.markdown("### 🎤 Audio Remoto")
    activar_mic = st.toggle("🔴 Activar Escucha", value=st.session_state.escuchando)
    
    if activar_mic != st.session_state.escuchando:
        st.session_state.escuchando = activar_mic
        # Enviar comando al dispositivo
        cmd = "ON" if activar_mic else "OFF"
        cliente_mqtt.publish(TOPIC_COMANDOS, cmd)
        
    st.caption("Al activar, la Raspberry enviará audio en tiempo real.")

# ==========================================
# 🔄 PROCESAMIENTO DE DATOS
# ==========================================
data = estado_compartido.ultimo_dato
tiempo_transcurrido = time.time() - estado_compartido.ultima_recepcion

# Columnas principales de Layout
col_estado, col_dispositivo = st.columns([1, 2])
estado_con = col_estado.empty()
info_hw = col_dispositivo.empty()

st.markdown("---")

# KPIs
col1, col2, col3, col4, col5, col6 = st.columns(6)
kpi_t = col1.empty()
kpi_h = col2.empty()
kpi_g = col3.empty()
kpi_d = col4.empty()
kpi_u = col5.empty()
kpi_r = col6.empty()

# Alertas
alert_banner = st.empty()
col_audio_live, col_audio_alertas = st.columns([1, 1])
audio_live_cont = col_audio_live.empty()
audio_alert_cont = col_audio_alertas.empty()

st.markdown("---")
col_extra1, col_extra2 = st.columns([1, 2])
tabla_sensores = col_extra1.empty()
graficos = col_extra2.empty()

# ==========================================
# 🖥️ LOGICA DE VISUALIZACIÓN
# ==========================================
if data and tiempo_transcurrido < TIEMPO_LIMITE_DESCONEXION:
    # 1. Extracción de datos
    t = data.get('temp', 0)
    h = data.get('hum', 0)
    g = data.get('gas_mq2', 1)
    d = data.get('distancia', 0)
    mov = data.get('movimiento_detectado', False)
    umbral = data.get('umbral_audio_actual', 0.50)
    
    hw = data.get('hardware', {})
    sensores = data.get('estado_sensores', {})
    
    # 2. Análisis
    prediccion = estado_compartido.detector_ia.predecir(t, h, g)
    riesgo = analizar_riesgo(t, g, h, d, prediccion, mov)
    
    # 3. Estado Conexión
    estado_con.success(f"🟢 **ONLINE** | Ping: {int(tiempo_transcurrido)}s")
    
    with info_hw.container():
        c1, c2, c3 = st.columns(3)
        c1.markdown(f"**🤖 Modelo:** {hw.get('modelo_rpi', 'RPi 3')}")
        c2.markdown(f"**🌡️ CPU:** {hw.get('cpu_temp', 0)}°C")
        c3.markdown(f"**📡 Host:** {hw.get('hostname', 'Forestal-1')}")

    # 4. KPIs
    kpi_t.metric("🌡️ Temp", f"{t}°C", delta_color="inverse" if t > 35 else "normal")
    kpi_h.metric("💧 Humedad", f"{h}%")
    
    gas_txt = "🔥 GAS!" if g == 0 else "✅ Aire Puro"
    kpi_g.metric("♨️ Calidad Aire", gas_txt, delta_color="inverse" if g == 0 else "normal")
    
    kpi_d.metric("📏 Distancia", f"{d}cm", delta_color="inverse" if 0 < d < 50 else "normal")
    
    # Lógica de colores solicitada para Umbral
    # 0.50 -> Verde (Normal) | 0.25 -> Rojo (Sensible/Alerta)
    color_umbral = "inverse" if umbral <= 0.25 else "normal"
    txt_umbral = "🚨 ALERTA" if umbral <= 0.25 else "🛡️ VIGILANCIA"
    kpi_u.metric("🎚️ Umbral IA", f"{umbral:.2f}", txt_umbral, delta_color=color_umbral)
    
    kpi_r.metric("⚡ Nivel Riesgo", f"{riesgo['score']}%", riesgo['nivel'], delta_color=riesgo['color'])

    # 5. Banner Alerta
    if riesgo['nivel'] == "CRÍTICO":
        alert_banner.error(f"## {riesgo['icono']} {riesgo['mensaje']}")
    elif riesgo['nivel'] == "ADVERTENCIA":
        alert_banner.warning(f"## {riesgo['icono']} {riesgo['mensaje']}")
    else:
        alert_banner.success(f"## {riesgo['icono']} {riesgo['mensaje']}")

    # 6. Tabla Sensores (Sincronizada con v6)
    with tabla_sensores.container():
        st.markdown("#### 📡 Estado de Sensores")
        
        # Mapeo de claves enviadas por RPi v6
        estado_dht = sensores.get('dht11', 'UNKNOWN')
        estado_ultra = sensores.get('ultrasonido', 'UNKNOWN')
        estado_mq2 = sensores.get('mq2', 'UNKNOWN')
        estado_mic = sensores.get('mic_inmp441', 'UNKNOWN')
        
        df_s = pd.DataFrame([
            {"Sensor": "DHT11 (Clima)", "Estado": estado_dht},
            {"Sensor": "HC-SR04 (Distancia)", "Estado": estado_ultra},
            {"Sensor": "MQ-2 (Gas)", "Estado": estado_mq2},
            {"Sensor": "INMP441 (Audio IA)", "Estado": estado_mic},
        ])
        
        # Estilizar tabla simple
        st.dataframe(df_s, hide_index=True, use_container_width=True)
        
        st.markdown("#### 🤖 Diagnóstico IA")
        if prediccion['es_anomalia']:
            st.error(f"Anomalía detectada ({prediccion['confianza']}%)")
        else:
            st.success("Patrones normales")

    # 7. Gráficos Históricos
    with graficos.container():
        if len(estado_compartido.hist_temp) > 2:
            df_hist = pd.DataFrame({
                "Temp (°C)": list(estado_compartido.hist_temp),
                "Humedad (%)": list(estado_compartido.hist_hum),
                "Gas (Dig)": list(estado_compartido.hist_gas)
            })
            st.line_chart(df_hist, height=250)

else:
    # OFFLINE
    estado_con.error(f"🔴 **OFFLINE** | Última vez hace: {int(tiempo_transcurrido)}s")
    info_hw.warning("Esperando conexión con Raspberry Pi...")
    alert_banner.info("⏳ Sistema en espera de datos...")

# ==========================================
# 🎤 SECCIÓN DE AUDIO (COMPARTIDA)
# ==========================================
with audio_live_cont.container():
    st.markdown("#### 🎧 Audio en Vivo")
    if st.session_state.escuchando:
        monitor_data = estado_compartido.ultimo_audio_monitor
        if monitor_data:
            ts_audio = datetime.fromtimestamp(monitor_data['timestamp']).strftime('%H:%M:%S')
            st.caption(f"🔊 Recibido a las {ts_audio}")
            audio_bytes = base64.b64decode(monitor_data['audio'])
            st.audio(audio_bytes, format='audio/wav', autoplay=True)
        else:
            st.warning("⏳ Esperando flujo de audio...")
    else:
        st.info("🔇 Transmisión desactivada")

with audio_alert_cont.container():
    st.markdown("#### 🚨 Últimos Disparos Detectados")
    if estado_compartido.alertas_disparo:
        # Mostrar solo la más reciente expandida
        alerta = estado_compartido.alertas_disparo[0]
        ts_alerta = datetime.fromtimestamp(alerta['timestamp']).strftime('%H:%M:%S')
        st.error(f"🔫 DISPARO - {ts_alerta}")
        st.metric("Probabilidad IA", f"{alerta['probabilidad']*100:.1f}%")
        
        audio_alerta = base64.b64decode(alerta['audio'])
        st.audio(audio_alerta, format='audio/wav')
        
        if len(estado_compartido.alertas_disparo) > 1:
            st.caption(f"Historial: {len(estado_compartido.alertas_disparo)} eventos guardados")
    else:
        st.success("✅ Sin incidentes de disparos")

# Recarga automática para efecto "Tiempo Real"
time.sleep(1)
st.rerun()
