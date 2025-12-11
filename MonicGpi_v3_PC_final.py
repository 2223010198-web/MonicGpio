# -*- coding: utf-8 -*-
"""
🌲 DASHBOARD FORESTAL INTEGRADO (DISEÑO GOOGLE MATERIAL DESIGN)
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
# 🎨 ESTILOS CSS MEJORADOS - GOOGLE MATERIAL DESIGN
# ==========================================
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;600;700;800&display=swap');
    
    /* Reset Global */
    .main { font-family: 'Inter', sans-serif; background: #f8f9fa; }
    
    /* Hero Header */
    .hero-container {
        background: linear-gradient(135deg, #0d7d3f 0%, #1a5f3a 50%, #0a3d26 100%);
        padding: 2rem 2rem 3rem 2rem;
        border-radius: 24px;
        margin-bottom: 2rem;
        box-shadow: 0 8px 32px rgba(13, 125, 63, 0.3);
        position: relative;
        overflow: hidden;
    }
    .hero-container::before {
        content: '';
        position: absolute;
        top: -50%;
        right: -20%;
        width: 500px;
        height: 500px;
        background: radial-gradient(circle, rgba(255,255,255,0.1) 0%, transparent 70%);
        border-radius: 50%;
    }
    .hero-title {
        font-size: 3.5rem;
        font-weight: 800;
        color: white;
        text-align: center;
        margin: 0;
        text-shadow: 0 4px 12px rgba(0,0,0,0.3);
        letter-spacing: -1px;
    }
    .hero-subtitle {
        text-align: center;
        color: rgba(255,255,255,0.9);
        font-size: 1.2rem;
        font-weight: 300;
        margin-top: 0.5rem;
    }
    .hero-status {
        text-align: center;
        margin-top: 1.5rem;
        display: flex;
        justify-content: center;
        gap: 2rem;
    }
    .hero-badge {
        background: rgba(255,255,255,0.15);
        backdrop-filter: blur(10px);
        padding: 0.5rem 1.5rem;
        border-radius: 50px;
        color: white;
        font-weight: 600;
        font-size: 0.9rem;
        border: 1px solid rgba(255,255,255,0.2);
    }
    
    /* Sistema de Alertas Crítico */
    .alert-critical {
        background: linear-gradient(135deg, #dc2626 0%, #991b1b 100%);
        padding: 2rem;
        border-radius: 20px;
        margin-bottom: 2rem;
        box-shadow: 0 12px 48px rgba(220, 38, 38, 0.4);
        animation: pulse-alert 2s infinite;
        border: 3px solid #fef2f2;
    }
    @keyframes pulse-alert {
        0%, 100% { box-shadow: 0 12px 48px rgba(220, 38, 38, 0.4); }
        50% { box-shadow: 0 16px 64px rgba(220, 38, 38, 0.6); }
    }
    .alert-critical h2 {
        color: white;
        font-size: 2rem;
        font-weight: 800;
        margin: 0;
        display: flex;
        align-items: center;
        gap: 1rem;
    }
    .alert-critical p {
        color: rgba(255,255,255,0.95);
        font-size: 1.1rem;
        margin-top: 0.5rem;
    }
    
    .alert-warning {
        background: linear-gradient(135deg, #f59e0b 0%, #d97706 100%);
        padding: 1.5rem;
        border-radius: 16px;
        margin-bottom: 2rem;
        box-shadow: 0 8px 32px rgba(245, 158, 11, 0.3);
        border: 2px solid #fef3c7;
    }
    .alert-warning h3 {
        color: white;
        font-size: 1.5rem;
        font-weight: 700;
        margin: 0;
    }
    
    /* Cards Modernos con Glassmorphism */
    .modern-card {
        background: white;
        border-radius: 20px;
        padding: 1.5rem;
        box-shadow: 0 4px 24px rgba(0,0,0,0.08);
        transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
        border: 1px solid rgba(0,0,0,0.05);
        height: 100%;
    }
    .modern-card:hover {
        transform: translateY(-4px);
        box-shadow: 0 12px 40px rgba(0,0,0,0.12);
    }
    .card-header {
        display: flex;
        justify-content: space-between;
        align-items: center;
        margin-bottom: 1rem;
    }
    .card-title {
        font-size: 0.85rem;
        font-weight: 700;
        color: #6b7280;
        text-transform: uppercase;
        letter-spacing: 0.5px;
    }
    .card-value {
        font-size: 2.5rem;
        font-weight: 800;
        color: #111827;
        line-height: 1;
        margin: 0.5rem 0;
    }
    .card-unit {
        font-size: 1rem;
        color: #9ca3af;
        font-weight: 500;
    }
    .card-trend {
        font-size: 0.9rem;
        font-weight: 600;
        padding: 0.25rem 0.75rem;
        border-radius: 12px;
        display: inline-block;
    }
    .trend-good { background: #d1fae5; color: #059669; }
    .trend-warning { background: #fef3c7; color: #d97706; }
    .trend-critical { background: #fee2e2; color: #dc2626; }
    
    /* Sensor Status Cards */
    .sensor-grid {
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
        gap: 1rem;
        margin-bottom: 2rem;
    }
    .sensor-status-card {
        background: white;
        border-radius: 16px;
        padding: 1.25rem;
        box-shadow: 0 2px 12px rgba(0,0,0,0.06);
        border-left: 4px solid #e5e7eb;
        transition: all 0.3s ease;
    }
    .sensor-status-card.online { border-left-color: #10b981; }
    .sensor-status-card.offline { border-left-color: #ef4444; }
    .sensor-status-card:hover {
        box-shadow: 0 4px 20px rgba(0,0,0,0.1);
    }
    .sensor-name {
        font-weight: 700;
        font-size: 1rem;
        color: #111827;
        margin-bottom: 0.25rem;
    }
    .sensor-model {
        font-size: 0.8rem;
        color: #9ca3af;
        margin-bottom: 0.75rem;
    }
    .sensor-indicator {
        display: inline-flex;
        align-items: center;
        gap: 0.5rem;
        padding: 0.35rem 0.85rem;
        border-radius: 20px;
        font-size: 0.8rem;
        font-weight: 600;
    }
    .sensor-indicator.online {
        background: #d1fae5;
        color: #059669;
    }
    .sensor-indicator.offline {
        background: #fee2e2;
        color: #dc2626;
    }
    
    /* Timeline de Eventos */
    .timeline-container {
        background: white;
        border-radius: 20px;
        padding: 1.5rem;
        box-shadow: 0 4px 24px rgba(0,0,0,0.08);
    }
    .timeline-item {
        display: flex;
        gap: 1rem;
        padding: 1rem 0;
        border-bottom: 1px solid #f3f4f6;
    }
    .timeline-item:last-child { border-bottom: none; }
    .timeline-icon {
        width: 40px;
        height: 40px;
        border-radius: 12px;
        display: flex;
        align-items: center;
        justify-content: center;
        font-size: 1.2rem;
        flex-shrink: 0;
    }
    .timeline-icon.critical { background: #fee2e2; }
    .timeline-icon.warning { background: #fef3c7; }
    .timeline-icon.info { background: #dbeafe; }
    .timeline-content h4 {
        margin: 0;
        font-size: 0.95rem;
        font-weight: 600;
        color: #111827;
    }
    .timeline-content p {
        margin: 0.25rem 0 0 0;
        font-size: 0.85rem;
        color: #6b7280;
    }
    
    /* Panel de IA */
    .ia-panel {
        background: linear-gradient(135deg, #3b82f6 0%, #1d4ed8 100%);
        border-radius: 20px;
        padding: 2rem;
        color: white;
        box-shadow: 0 8px 32px rgba(59, 130, 246, 0.3);
    }
    .ia-panel h3 {
        margin: 0 0 1rem 0;
        font-size: 1.3rem;
        font-weight: 700;
    }
    .ia-status {
        background: rgba(255,255,255,0.15);
        backdrop-filter: blur(10px);
        padding: 1rem;
        border-radius: 12px;
        margin-bottom: 1rem;
        border: 1px solid rgba(255,255,255,0.2);
    }
    .ia-confidence {
        display: flex;
        justify-content: space-between;
        align-items: center;
        margin-top: 0.75rem;
    }
    .confidence-bar {
        flex: 1;
        height: 8px;
        background: rgba(255,255,255,0.3);
        border-radius: 4px;
        overflow: hidden;
        margin: 0 1rem;
    }
    .confidence-fill {
        height: 100%;
        background: white;
        border-radius: 4px;
        transition: width 0.5s ease;
    }
    
    /* Audio Player Moderno */
    .audio-container {
        background: white;
        border-radius: 20px;
        padding: 1.5rem;
        box-shadow: 0 4px 24px rgba(0,0,0,0.08);
    }
    .audio-header {
        display: flex;
        justify-content: space-between;
        align-items: center;
        margin-bottom: 1rem;
    }
    .audio-status {
        display: flex;
        align-items: center;
        gap: 0.5rem;
        padding: 0.5rem 1rem;
        background: #f3f4f6;
        border-radius: 20px;
        font-size: 0.85rem;
        font-weight: 600;
    }
    .audio-live {
        width: 8px;
        height: 8px;
        background: #ef4444;
        border-radius: 50%;
        animation: pulse-live 2s infinite;
    }
    @keyframes pulse-live {
        0%, 100% { opacity: 1; }
        50% { opacity: 0.4; }
    }
    
    /* Métricas con Iconos */
    .metric-icon-card {
        display: flex;
        align-items: center;
        gap: 1rem;
    }
    .metric-icon {
        width: 56px;
        height: 56px;
        border-radius: 14px;
        display: flex;
        align-items: center;
        justify-content: center;
        font-size: 1.8rem;
        flex-shrink: 0;
    }
    .metric-icon.temp { background: linear-gradient(135deg, #f97316 0%, #ea580c 100%); }
    .metric-icon.humidity { background: linear-gradient(135deg, #06b6d4 0%, #0891b2 100%); }
    .metric-icon.gas { background: linear-gradient(135deg, #8b5cf6 0%, #7c3aed 100%); }
    .metric-icon.distance { background: linear-gradient(135deg, #ec4899 0%, #db2777 100%); }
    
    /* Sección de Título */
    .section-header {
        font-size: 1.5rem;
        font-weight: 700;
        color: #111827;
        margin: 2rem 0 1rem 0;
        display: flex;
        align-items: center;
        gap: 0.75rem;
    }
    .section-divider {
        height: 2px;
        background: linear-gradient(90deg, #e5e7eb 0%, transparent 100%);
        margin: 2rem 0;
    }
    
    /* Responsive */
    @media (max-width: 768px) {
        .hero-title { font-size: 2rem; }
        .card-value { font-size: 2rem; }
    }
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
        self.hist_distancia = deque(maxlen=50)
        self.hist_riesgo = deque(maxlen=50)
        
        # Alertas
        self.alertas_disparo = deque(maxlen=5)
        self.eventos_timeline = deque(maxlen=10)
        
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
                estado.hist_distancia.append(payload.get('distancia', 0))
                
                estado.detector_ia.agregar_muestra(
                    payload.get('temp', 0), 
                    payload.get('hum', 0), 
                    payload.get('gas_mq2', 0)
                )

            elif topic == TOPIC_ALERTAS:
                estado.alertas_disparo.appendleft(payload)
                # Agregar a timeline
                estado.eventos_timeline.appendleft({
                    'tipo': 'critical',
                    'icono': '🔫',
                    'titulo': 'DISPARO DETECTADO',
                    'descripcion': f"Probabilidad: {payload['probabilidad']*100:.1f}%",
                    'timestamp': payload['timestamp']
                })
            
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
    alertas = []
    
    # 1. Temperatura
    if temp > 45: 
        score += 40
        factores.append("🔥 Temperatura crítica")
        alertas.append(('critical', 'TEMPERATURA EXTREMA', f'{temp}°C detectados'))
    elif temp > 35: 
        score += 20
        factores.append("⚠️ Temperatura elevada")
    
    # 2. Gas (0 = Detectado)
    if gas_mq2 == 0: 
        score += 45
        factores.append("🔥 GAS/HUMO DETECTADO")
        alertas.append(('critical', 'GAS O HUMO DETECTADO', 'Posible inicio de incendio'))
    
    # 3. Humedad
    if hum < 20: 
        score += 15
        factores.append("💧 Aire muy seco")
        alertas.append(('warning', 'HUMEDAD BAJA', f'{hum}% - Riesgo aumentado'))
    
    # 4. IA
    if prediccion_ia["es_anomalia"]: 
        score += 20
        factores.append("🤖 Patrón anómalo (IA)")
        alertas.append(('warning', 'ANOMALÍA DETECTADA', 'Patrón inusual en sensores'))
    
    # 5. Movimiento
    if movimiento:
        score += 10
        factores.append("⚡ Movimiento detectado")
        alertas.append(('info', 'MOVIMIENTO', 'Actividad detectada en zona'))
    
    # 6. Proximidad CRÍTICA (50cm)
    if 0 < distancia < 50:
        score += 25
        factores.append(f"🚶 PROXIMIDAD CRÍTICA: {distancia}cm")
        alertas.append(('critical', 'OBJETO/PERSONA CERCANA', f'A {distancia}cm del sensor'))
    elif 50 <= distancia < 100:
        factores.append(f"👁️ Objeto detectado: {distancia}cm")
    
    # Agregar eventos a timeline
    for tipo, titulo, desc in alertas:
        estado_compartido.eventos_timeline.appendleft({
            'tipo': tipo,
            'icono': '🔥' if tipo == 'critical' else ('⚠️' if tipo == 'warning' else 'ℹ️'),
            'titulo': titulo,
            'descripcion': desc,
            'timestamp': time.time()
        })
    
    # Evaluación Final
    if score >= 60:
        return {
            "nivel": "CRÍTICO", 
            "color": "inverse", 
            "icono": "🔥", 
            "mensaje": "¡PELIGRO INMINENTE!", 
            "score": score, 
            "factores": factores,
            "alertas": alertas
        }
    elif score >= 30:
        return {
            "nivel": "ADVERTENCIA", 
            "color": "off", 
            "icono": "⚠️", 
            "mensaje": "Precaución Necesaria", 
            "score": score, 
            "factores": factores,
            "alertas": alertas
        }
    else:
        return {
            "nivel": "NORMAL", 
            "color": "normal", 
            "icono": "✅", 
            "mensaje": "Zona Segura", 
            "score": score, 
            "factores": factores,
            "alertas": []
        }

# ==========================================
# 🎛️ SIDEBAR
# ==========================================
if 'audio_local_activo' not in st.session_state:
    st.session_state.audio_local_activo = False

with st.sidebar:
    st.markdown("### ⚙️ Centro de Control")
    st.markdown("---")
    
    # Estado del Sistema
    st.markdown("#### 📡 Conexión")
    col1, col2 = st.columns(2)
    col1.metric("Broker", "HiveMQ", "🟢 Online")
    col2.metric("Latencia", f"{int((time.time() - estado_compartido.ultima_recepcion)*1000)}ms")
    
    st.markdown("---")
    st.markdown("#### 🎧 Audio Táctico")
    
    escuchar = st.toggle("📈 Transmisión en Vivo", value=st.session_state.audio_local_activo)
    
    if escuchar != st.session_state.audio_local_activo:
        st.session_state.audio_local_activo = escuchar
        if escuchar:
            cliente_mqtt.publish(TOPIC_COMANDOS, "ON")
            st.toast("🎧 Audio conectado", icon="✅")
        else:
            st.toast("🔇 Audio desactivado", icon="ℹ️")
    
    st.markdown("---")
    st.markdown("#### 📊 Estadísticas")
    if estado_compartido.ultimo_dato:
        st.metric("Muestras IA", len(estado_compartido.detector_ia.historial))
        st.metric("Eventos", len(estado_compartido.eventos_timeline))
    
    st.markdown("---")
    st.caption("🌲 Forest Monitor Pro v2.0")
    st.caption("Powered by Google Design")

# ==========================================
# 🖥️ MAIN DASHBOARD
# ==========================================

# Hero Header
data = estado_compartido.ultimo_dato
tiempo_transcurrido = time.time() - estado_compartido.ultima_recepcion

if data and tiempo_transcurrido < TIEMPO_LIMITE_DESCONEXION:
    hw = data.get('hardware', {})
    
    st.markdown(f"""
    <div class="hero-container">
        <h1 class="hero-title">🌲 Monitor Forestal Pro</h1>
        <p class="hero-subtitle">Sistema Inteligente de Vigilancia Ambiental y Seguridad</p>
        <div class="hero-status">
            <div class="hero-badge">🟢 SISTEMA OPERATIVO</div>
            <div class="hero-badge">⚡ {int(tiempo_transcurrido*1000)}ms latencia</div>
            <div class="hero-badge">💻 {hw.get('modelo_rpi', 'RPi')} @ {hw.get('cpu_temp', 0)}°C</div>
        </div>
    </div>
    """, unsafe_allow_html=True)
    
    # Extraer datos
    t = data.get('temp', 0)
    h = data.get('hum', 0)
    g = data.get('gas_mq2', 1)
    d = data.get('distancia', 0)
    mov = data.get('movimiento_detectado', False)
    umbral = data.get('umbral_audio_actual', 0.50)
    sensores = data.get('estado_sensores', {})
    
    # IA y Riesgo
    prediccion = estado_compartido.detector_ia.predecir(t, h, g)
    riesgo = analizar_riesgo(t, g, h, d, prediccion, mov)
    estado_compartido.hist_riesgo.append(riesgo['score'])
    
    # ==========================================
    # 🚨 SISTEMA DE ALERTAS CRÍTICAS
    # ==========================================
    
    # Alerta Crítica de Incendio
    if riesgo['score'] >= 60 or g == 0:
        st.markdown(f"""
        <div class="alert-critical">
            <h2>🔥 ALERTA CRÍTICA DE INCENDIO</h2>
            <p>Nivel de riesgo: <strong>{riesgo['score']}/100</strong> | {riesgo['mensaje']}</p>
            <p>Factores detectados: {' • '.join(riesgo['factores'])}</p>
        </div>
        """, unsafe_allow_html=True)
    
    # Alerta de Disparo
    if estado_compartido.alertas_disparo:
        last_shot = estado_compartido.alertas_disparo[0]
        ts_shot = datetime.fromtimestamp(last_shot['timestamp']).strftime('%H:%M:%S')
        st.markdown(f"""
        <div class="alert-critical">
            <h2>🔫 DISPARO DETECTADO</h2>
            <p>Hora: <strong>{ts_shot}</strong> | Confianza IA: <strong>{last_shot['probabilidad']*100:.1f}%</strong></p>
            <p>⚠️ Posible actividad de caza furtiva en la zona</p>
        </div>
        """, unsafe_allow_html=True)
        st.audio(base64.b64decode(last_shot['audio']), format='audio/wav')
    
    # Alerta de Proximidad Crítica
    if 0 < d < 50:
        st.markdown(f"""
        <div class="alert-warning">
            <h3>🚶 PROXIMIDAD CRÍTICA DETECTADA</h3>
            <p>Objeto/Persona a <strong>{d} cm</strong> del sensor ultrasonido</p>
            <p>Posible intruso o cazador furtivo en el área protegida</p>
        </div>
        """, unsafe_allow_html=True)
    
    # Advertencia General
    elif riesgo['score'] >= 30:
        st.markdown(f"""
        <div class="alert-warning">
            <h3>⚠️ ADVERTENCIA - Nivel {riesgo['nivel']}</h3>
            <p>{riesgo['mensaje']} | Score: {riesgo['score']}/100</p>
        </div>
        """, unsafe_allow_html=True)
    
    st.markdown('<div class="section-divider"></div>', unsafe_allow_html=True)
    
    # ==========================================
    # 📊 MÉTRICAS PRINCIPALES CON ICONOS
    # ==========================================
    st.markdown('<h2 class="section-header">📊 Métricas Ambientales</h2>', unsafe_allow_html=True)
    
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        trend_t = "trend-critical" if t > 35 else ("trend-warning" if t > 30 else "trend-good")
        st.markdown(f"""
        <div class="modern-card">
            <div class="metric-icon-card">
                <div class="metric-icon temp">🌡️</div>
                <div>
                    <div class="card-title">TEMPERATURA</div>
                    <div class="card-value">{t}<span class="card-unit">°C</span></div>
                    <span class="card-trend {trend_t}">
                        {'🔥 CRÍTICO' if t > 35 else ('⚠️ Alto' if t > 30 else '✅ Normal')}
                    </span>
                </div>
            </div>
        </div>
        """, unsafe_allow_html=True)
    
    with col2:
        trend_h = "trend-critical" if h < 20 else ("trend-warning" if h < 40 else "trend-good")
        st.markdown(f"""
        <div class="modern-card">
            <div class="metric-icon-card">
                <div class="metric-icon humidity">💧</div>
                <div>
                    <div class="card-title">HUMEDAD</div>
                    <div class="card-value">{h}<span class="card-unit">%</span></div>
                    <span class="card-trend {trend_h}">
                        {'⚠️ Muy Seco' if h < 20 else ('💧 Bajo' if h < 40 else '✅ Óptimo')}
                    </span>
                </div>
            </div>
        </div>
        """, unsafe_allow_html=True)
    
    with col3:
        gas_status = "DETECTADO" if g == 0 else "Normal"
        trend_g = "trend-critical" if g == 0 else "trend-good"
        st.markdown(f"""
        <div class="modern-card">
            <div class="metric-icon-card">
                <div class="metric-icon gas">♨️</div>
                <div>
                    <div class="card-title">GAS/HUMO</div>
                    <div class="card-value" style="font-size: 1.8rem;">{gas_status}</div>
                    <span class="card-trend {trend_g}">
                        {'🔥 ALERTA' if g == 0 else '✅ Despejado'}
                    </span>
                </div>
            </div>
        </div>
        """, unsafe_allow_html=True)
    
    with col4:
        dist_status = f"{d} cm" if d > 0 else "Sin obj."
        trend_d = "trend-critical" if 0 < d < 50 else ("trend-warning" if 50 <= d < 100 else "trend-good")
        st.markdown(f"""
        <div class="modern-card">
            <div class="metric-icon-card">
                <div class="metric-icon distance">📏</div>
                <div>
                    <div class="card-title">DISTANCIA</div>
                    <div class="card-value" style="font-size: 1.8rem;">{dist_status}</div>
                    <span class="card-trend {trend_d}">
                        {'🚨 CRÍTICO' if 0 < d < 50 else ('👁️ Cerca' if 50 <= d < 100 else '✅ Lejano')}
                    </span>
                </div>
            </div>
        </div>
        """, unsafe_allow_html=True)
    
    st.markdown('<div style="margin: 1.5rem 0;"></div>', unsafe_allow_html=True)
    
    # Métricas Secundarias
    col5, col6, col7 = st.columns(3)
    
    with col5:
        st.markdown(f"""
        <div class="modern-card">
            <div class="card-title">🎚️ UMBRAL AUDIO IA</div>
            <div class="card-value">{umbral:.2f}</div>
            <span class="card-trend {'trend-critical' if umbral <= 0.25 else 'trend-good'}">
                {'🚨 MÁXIMA ALERTA' if umbral <= 0.25 else '🛡️ VIGILANCIA'}
            </span>
        </div>
        """, unsafe_allow_html=True)
    
    with col6:
        st.markdown(f"""
        <div class="modern-card">
            <div class="card-title">⚡ ÍNDICE DE RIESGO</div>
            <div class="card-value">{riesgo['score']}<span class="card-unit">/100</span></div>
            <span class="card-trend trend-{'critical' if riesgo['score'] >= 60 else ('warning' if riesgo['score'] >= 30 else 'good')}">
                {riesgo['icono']} {riesgo['nivel']}
            </span>
        </div>
        """, unsafe_allow_html=True)
    
    with col7:
        mov_status = "DETECTADO" if mov else "Sin actividad"
        st.markdown(f"""
        <div class="modern-card">
            <div class="card-title">🎯 MOVIMIENTO</div>
            <div class="card-value" style="font-size: 1.6rem;">{mov_status}</div>
            <span class="card-trend {'trend-warning' if mov else 'trend-good'}">
                {'⚡ ACTIVO' if mov else '✅ TRANQUILO'}
            </span>
        </div>
        """, unsafe_allow_html=True)
    
    st.markdown('<div class="section-divider"></div>', unsafe_allow_html=True)
    
    # ==========================================
    # 📡 ESTADO DE SENSORES
    # ==========================================
    st.markdown('<h2 class="section-header">📡 Estado de Dispositivos</h2>', unsafe_allow_html=True)
    
    sensores_info = [
        ("Sensor Climático", "DHT11 Digital", sensores.get('dht11', 'OFFLINE')),
        ("Sensor de Proximidad", "HC-SR04 Ultrasónico", sensores.get('ultrasonido', 'OFFLINE')),
        ("Detector Gas/Humo", "MQ-2 Analógico", sensores.get('mq2', 'OFFLINE')),
        ("Micrófono Táctico", "INMP441 I2S Digital", sensores.get('mic_inmp441', 'OFFLINE'))
    ]
    
    cols = st.columns(4)
    for idx, (nombre, modelo, estado) in enumerate(sensores_info):
        with cols[idx]:
            conectado = False
            if isinstance(estado, dict):
                conectado = estado.get('conectado', False)
                if not conectado and "ONLINE" in str(estado): conectado = True
            else:
                conectado = (str(estado) == "ONLINE")
            
            status_class = "online" if conectado else "offline"
            status_text = "ONLINE" if conectado else "OFFLINE"
            icon = "🟢" if conectado else "🔴"
            
            st.markdown(f"""
            <div class="sensor-status-card {status_class}">
                <div class="sensor-name">{icon} {nombre}</div>
                <div class="sensor-model">{modelo}</div>
                <span class="sensor-indicator {status_class}">{status_text}</span>
            </div>
            """, unsafe_allow_html=True)
    
    st.markdown('<div class="section-divider"></div>', unsafe_allow_html=True)
    
    # ==========================================
    # 📈 GRÁFICOS Y ANÁLISIS
    # ==========================================
    st.markdown('<h2 class="section-header">📈 Análisis Temporal</h2>', unsafe_allow_html=True)
    
    col_graf1, col_graf2 = st.columns(2)
    
    with col_graf1:
        st.markdown('<div class="modern-card">', unsafe_allow_html=True)
        st.markdown("#### 🌡️ Temperatura y Humedad")
        if len(estado_compartido.hist_temp) > 0:
            df_clima = pd.DataFrame({
                "Temperatura (°C)": list(estado_compartido.hist_temp),
                "Humedad (%)": list(estado_compartido.hist_hum)
            })
            st.area_chart(df_clima, height=250, color=["#f97316", "#06b6d4"])
        else:
            st.info("Recopilando datos...")
        st.markdown('</div>', unsafe_allow_html=True)
    
    with col_graf2:
        st.markdown('<div class="modern-card">', unsafe_allow_html=True)
        st.markdown("#### 📏 Distancia Detectada")
        if len(estado_compartido.hist_distancia) > 0:
            df_dist = pd.DataFrame({
                "Distancia (cm)": list(estado_compartido.hist_distancia)
            })
            st.line_chart(df_dist, height=250, color="#ec4899")
            # Línea de referencia crítica
            st.caption("🚨 Zona crítica: < 50cm | ⚠️ Zona advertencia: 50-100cm")
        else:
            st.info("Recopilando datos...")
        st.markdown('</div>', unsafe_allow_html=True)
    
    st.markdown('<div style="margin: 1rem 0;"></div>', unsafe_allow_html=True)
    
    col_graf3, col_graf4 = st.columns(2)
    
    with col_graf3:
        st.markdown('<div class="modern-card">', unsafe_allow_html=True)
        st.markdown("#### ♨️ Nivel de Gas/Humo")
        if len(estado_compartido.hist_gas) > 0:
            df_gas = pd.DataFrame({
                "Estado Gas": list(estado_compartido.hist_gas)
            })
            st.line_chart(df_gas, height=250, color="#8b5cf6")
            st.caption("🔥 0 = Gas/Humo detectado | 1 = Aire limpio")
        else:
            st.info("Recopilando datos...")
        st.markdown('</div>', unsafe_allow_html=True)
    
    with col_graf4:
        st.markdown('<div class="modern-card">', unsafe_allow_html=True)
        st.markdown("#### ⚡ Evolución del Riesgo")
        if len(estado_compartido.hist_riesgo) > 0:
            df_riesgo = pd.DataFrame({
                "Score de Riesgo": list(estado_compartido.hist_riesgo)
            })
            st.area_chart(df_riesgo, height=250, color="#dc2626")
            st.caption("🟢 0-29: Seguro | 🟡 30-59: Precaución | 🔴 60-100: Crítico")
        else:
            st.info("Recopilando datos...")
        st.markdown('</div>', unsafe_allow_html=True)
    
    st.markdown('<div class="section-divider"></div>', unsafe_allow_html=True)
    
    # ==========================================
    # 🎧 AUDIO Y EVENTOS
    # ==========================================
    st.markdown('<h2 class="section-header">🎧 Monitoreo en Tiempo Real</h2>', unsafe_allow_html=True)
    
    col_audio, col_timeline = st.columns([1, 1])
    
    with col_audio:
        st.markdown('<div class="audio-container">', unsafe_allow_html=True)
        st.markdown("""
        <div class="audio-header">
            <h3 style="margin: 0; font-size: 1.2rem; font-weight: 700;">🎧 Audio Táctico</h3>
            <div class="audio-status">
                <div class="audio-live"></div>
                EN VIVO
            </div>
        </div>
        """, unsafe_allow_html=True)
        
        if st.session_state.audio_local_activo:
            audio_data = estado_compartido.ultimo_audio_monitor
            if audio_data:
                ts = datetime.fromtimestamp(audio_data['timestamp']).strftime('%H:%M:%S')
                st.caption(f"📡 Stream activo • {ts}")
                st.audio(base64.b64decode(audio_data['audio']), format='audio/wav', autoplay=True)
            else:
                st.warning("⏳ Esperando transmisión...")
        else:
            st.info("🔇 Audio desactivado\n\nActiva el toggle en el panel lateral para escuchar")
        
        st.markdown('</div>', unsafe_allow_html=True)
    
    with col_timeline:
        st.markdown('<div class="timeline-container">', unsafe_allow_html=True)
        st.markdown('<h3 style="margin: 0 0 1rem 0; font-size: 1.2rem; font-weight: 700;">📋 Timeline de Eventos</h3>', unsafe_allow_html=True)
        
        if estado_compartido.eventos_timeline:
            for evento in list(estado_compartido.eventos_timeline)[:5]:
                ts_ev = datetime.fromtimestamp(evento['timestamp']).strftime('%H:%M:%S')
                icon_class = evento['tipo']
                st.markdown(f"""
                <div class="timeline-item">
                    <div class="timeline-icon {icon_class}">{evento['icono']}</div>
                    <div class="timeline-content">
                        <h4>{evento['titulo']}</h4>
                        <p>{evento['descripcion']} • {ts_ev}</p>
                    </div>
                </div>
                """, unsafe_allow_html=True)
        else:
            st.info("✅ Sin eventos recientes\n\nEl sistema está monitoreando...")
        
        st.markdown('</div>', unsafe_allow_html=True)
    
    st.markdown('<div class="section-divider"></div>', unsafe_allow_html=True)
    
    # ==========================================
    # 🤖 PANEL DE INTELIGENCIA ARTIFICIAL
    # ==========================================
    st.markdown('<h2 class="section-header">🤖 Análisis de Inteligencia Artificial</h2>', unsafe_allow_html=True)
    
    col_ia1, col_ia2 = st.columns([2, 1])
    
    with col_ia1:
        st.markdown(f"""
        <div class="ia-panel">
            <h3>🧠 Motor de Detección de Anomalías</h3>
            <div class="ia-status">
                <div style="display: flex; justify-content: space-between; align-items: center;">
                    <span style="font-size: 1.1rem; font-weight: 600;">{prediccion['mensaje']}</span>
                    <span style="font-size: 1.5rem;">{'⚠️' if prediccion['es_anomalia'] else '✅'}</span>
                </div>
                <div class="ia-confidence">
                    <span style="font-weight: 600;">Confianza:</span>
                    <div class="confidence-bar">
                        <div class="confidence-fill" style="width: {prediccion['confianza']}%;"></div>
                    </div>
                    <span style="font-weight: 700; font-size: 1.2rem;">{prediccion['confianza']}%</span>
                </div>
            </div>
            <div style="margin-top: 1rem; padding: 1rem; background: rgba(255,255,255,0.1); border-radius: 8px;">
                <p style="margin: 0; font-size: 0.9rem; opacity: 0.9;">
                    <strong>Estado del Modelo:</strong> {'🟢 Entrenado' if estado_compartido.detector_ia.entrenado else '🟡 Calibrando'}<br>
                    <strong>Muestras:</strong> {len(estado_compartido.detector_ia.historial)}/50<br>
                    <strong>Algoritmo:</strong> Isolation Forest (Scikit-learn)
                </p>
            </div>
        </div>
        """, unsafe_allow_html=True)
    
    with col_ia2:
        st.markdown('<div class="modern-card">', unsafe_allow_html=True)
        st.markdown("#### 🎯 Factores de Riesgo")
        if riesgo['factores']:
            for factor in riesgo['factores']:
                st.markdown(f"• {factor}")
        else:
            st.success("✅ Sin factores de riesgo")
        
        st.markdown("---")
        st.markdown("#### 📊 Resumen")
        st.metric("Score Total", f"{riesgo['score']}/100")
        st.metric("Nivel", riesgo['nivel'])
        st.markdown('</div>', unsafe_allow_html=True)

else:
    # ==========================================
    # 🔴 SISTEMA OFFLINE
    # ==========================================
    st.markdown(f"""
    <div class="hero-container" style="background: linear-gradient(135deg, #dc2626 0%, #991b1b 100%);">
        <h1 class="hero-title">🔴 Sistema Desconectado</h1>
        <p class="hero-subtitle">No se reciben datos de la Raspberry Pi</p>
        <div class="hero-status">
            <div class="hero-badge">⏱️ Última conexión: hace {int(tiempo_transcurrido)}s</div>
        </div>
    </div>
    """, unsafe_allow_html=True)
    
    st.error("""
    ### ⚠️ Diagnóstico de Conexión
    
    El sistema no está recibiendo datos. Posibles causas:
    
    1. **Raspberry Pi apagada** - Verifica la alimentación eléctrica
    2. **Sin conexión a Internet** - Revisa la red WiFi
    3. **Error en el broker MQTT** - Verifica credenciales
    4. **Código de RPi detenido** - Reinicia el servicio
    
    **Acciones recomendadas:**
    - Verifica el LED de la Raspberry Pi
    - Prueba hacer ping a la RPi
    - Revisa los logs del sistema
    - Reinicia la Raspberry Pi
    """)

# Auto-refresh
time.sleep(1)
st.rerun()
    
