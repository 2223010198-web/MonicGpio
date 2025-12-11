# -*- coding: utf-8 -*-
"""
🌲 DASHBOARD FORESTAL INTEGRADO (MODO OSCURO NATIVO)
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
    page_title="MonicGpi",
    page_icon="🌲",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ==========================================
# 🎨 ESTILOS CSS MÍNIMOS
# ==========================================
st.markdown("""
<style>
    /* Animación para alertas críticas */
    @keyframes pulse-alert {
        0%, 100% { opacity: 1; }
        50% { opacity: 0.7; }
    }
    .pulse-alert {
        animation: pulse-alert 2s infinite;
    }
    
    /* Mejora legibilidad de tablas */
    .stDataFrame {
        font-size: 0.9rem;
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
    st.divider()
    
    # Estado del Sistema
    st.markdown("#### 📡 Conexión")
    col1, col2 = st.columns(2)
    col1.metric("Broker", "HiveMQ", "🟢 Online")
    col2.metric("Latencia", f"{int((time.time() - estado_compartido.ultima_recepcion)*1000)}ms")
    
    st.divider()
    st.markdown("#### 🎧 Audio Táctico")
    
    escuchar = st.toggle("📈 Transmisión en Vivo", value=st.session_state.audio_local_activo)
    
    if escuchar != st.session_state.audio_local_activo:
        st.session_state.audio_local_activo = escuchar
        if escuchar:
            cliente_mqtt.publish(TOPIC_COMANDOS, "ON")
            st.toast("🎧 Audio conectado", icon="✅")
        else:
            st.toast("🔇 Audio desactivado", icon="ℹ️")
    
    st.divider()
    st.markdown("#### 📊 Estadísticas")
    if estado_compartido.ultimo_dato:
        st.metric("Muestras IA", len(estado_compartido.detector_ia.historial))
        st.metric("Eventos", len(estado_compartido.eventos_timeline))
    
    st.divider()
    st.caption("🌲 Forest Monitor Pro v2.0")
    st.caption("Powered by Streamlit Dark Mode")

# ==========================================
# 🖥️ MAIN DASHBOARD
# ==========================================

data = estado_compartido.ultimo_dato
tiempo_transcurrido = time.time() - estado_compartido.ultima_recepcion

if data and tiempo_transcurrido < TIEMPO_LIMITE_DESCONEXION:
    
    # ==========================================
    # 📊 HEADER
    # ==========================================
    st.title("🌲 MonicGpi")
    st.caption("Sistema Inteligente de Vigilancia Ambiental y Seguridad")
    
    hw = data.get('hardware', {})
    col_h1, col_h2, col_h3 = st.columns(3)
    col_h1.metric("Estado", "OPERATIVO", "🟢 Online")
    col_h2.metric("Latencia", f"{int(tiempo_transcurrido*1000)}ms")
    col_h3.metric("Hardware", f"{hw.get('modelo_rpi', 'RPi')}", f"{hw.get('cpu_temp', 0)}°C")
    
    st.divider()
    
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
    # 📊 MÉTRICAS PRINCIPALES
    # ==========================================
    st.subheader("📊 Métricas Ambientales")

    # Primera fila: 5 columnas
    col1, col2, col3, col4, col5 = st.columns(5)

    with col1:
        delta_t = "🔥 CRÍTICO" if t > 35 else ("⚠️ Alto" if t > 30 else "✅ Normal")
        col1.metric(
            label="🌡️ TEMPERATURA",
            value=f"{t}°C",
            delta=delta_t,
            delta_color="inverse" if t > 35 else ("off" if t > 30 else "normal")
        )

    with col2:
        delta_h = "⚠️ Muy Seco" if h < 20 else ("💧 Bajo" if h < 40 else "✅ Óptimo")
        col2.metric(
            label="💧 HUMEDAD",
            value=f"{h}%",
            delta=delta_h,
            delta_color="inverse" if h < 20 else ("off" if h < 40 else "normal")
        )

    with col3:
        gas_status = "DETECTADO" if g == 0 else "Normal"
        delta_g = "🔥 ALERTA" if g == 0 else "✅ Despejado"
        col3.metric(
            label="♨️ GAS/HUMO",
            value=gas_status,
            delta=delta_g,
            delta_color="inverse" if g == 0 else "normal"
        )

    with col4:
        dist_status = f"{d} cm" if d > 0 else "Sin obj."
        delta_d = "🚨 CRÍTICO" if 0 < d < 50 else ("👁️ Cerca" if 50 <= d < 100 else "✅ Lejano")
        col4.metric(
            label="📏 DISTANCIA",
            value=dist_status,
            delta=delta_d,
            delta_color="inverse" if 0 < d < 50 else ("off" if 50 <= d < 100 else "normal")
        )

    with col5:
        delta_u = "🚨 MÁXIMA ALERTA" if umbral <= 0.25 else "🛡️ VIGILANCIA"
        col5.metric(
            label="🎚️ UMBRAL AUDIO IA",
            value=f"{umbral:.2f}",
            delta=delta_u,
            delta_color="inverse" if umbral <= 0.25 else "normal"
        )

    # Segunda fila: 2 métricas centradas con columnas espaciadoras
    _ ,_, col6, col7, _ = st.columns([1, 1, 2, 2, 1])

    with col6:
        col6.metric(
            label="⚡ ÍNDICE DE RIESGO",
            value=f"{riesgo['score']}/100",
            delta=f"{riesgo['icono']} {riesgo['nivel']}",
            delta_color="inverse" if riesgo['score'] >= 60 else ("off" if riesgo['score'] >= 30 else "normal")
        )

    with col7:
        mov_status = "DETECTADO" if mov else "Sin actividad"
        delta_m = "⚡ ACTIVO" if mov else "✅ TRANQUILO"
        col7.metric(
            label="🎯 MOVIMIENTO",
            value=mov_status,
            delta=delta_m,
            delta_color="off" if mov else "normal"
        )

    st.divider()

        # ==========================================
    # 🚨 SISTEMA DE ALERTAS CRÍTICAS
    # ==========================================
    
    # Alerta Crítica de Incendio
    if riesgo['score'] >= 60 or g == 0:
        st.error(f"""
        ### 🔥 ALERTA CRÍTICA DE INCENDIO
        
        **Nivel de riesgo:** {riesgo['score']}/100 | {riesgo['mensaje']}
        
        **Factores detectados:**
        {chr(10).join('- ' + f for f in riesgo['factores'])}
        """, icon="🚨")
    
    # Alerta de Disparo
    if estado_compartido.alertas_disparo:
        last_shot = estado_compartido.alertas_disparo[0]
        ts_shot = datetime.fromtimestamp(last_shot['timestamp']).strftime('%H:%M:%S')
        st.error(f"""
        ### DISPARO DETECTADO
        
        **Hora:** {ts_shot} | **Confianza IA:** {last_shot['probabilidad']*100:.1f}%
        
        ⚠️ Posible actividad de caza furtiva en la zona
        """, icon="🔥")
        st.audio(base64.b64decode(last_shot['audio']), format='audio/wav')
    
    # Alerta de Proximidad Crítica
    if 'tiempo_alerta_proximidad' not in st.session_state:
        st.session_state.tiempo_alerta_proximidad = 0

    # 2. Si detecta algo AHORA, actualizamos el temporizador al momento actual
    if 0 < d < 50:
        st.session_state.tiempo_alerta_proximidad = time.time()

    # 3. Mostrar la alerta si han pasado menos de 60 segundos desde la última detección
    tiempo_transcurrido_alerta = time.time() - st.session_state.tiempo_alerta_proximidad
    
    if tiempo_transcurrido_alerta < 60:
        tiempo_restante = int(60 - tiempo_transcurrido_alerta)
        
        st.warning(f"""
        ### 🚶 PROXIMIDAD CRÍTICA DETECTADA
        
        Se detectó un objeto/persona a **{d if 0 < d < 50 else 'menos de 50'} cm**.
        
        ⚠️ **Alerta activa por: {tiempo_restante}s**
        
        Posible intruso o cazador furtivo en el área protegida.
        """, icon="⚠️")
    
    # Advertencia General
    elif riesgo['score'] >= 30:
        st.warning(f"""
        ### ⚠️ ADVERTENCIA - Nivel {riesgo['nivel']}
        
        {riesgo['mensaje']} | Score: {riesgo['score']}/100
        """, icon="⚠️")
    
    st.divider()
        
    # ==========================================
    # 📡 ESTADO DE SENSORES
    # ==========================================
    st.subheader("📡 Estado de Dispositivos")
    
    sensores_data = []
    sensores_info = [
        ("🌡️ Sensor Climático", "DHT11 Digital", sensores.get('dht11', 'OFFLINE')),
        ("📏 Sensor de Proximidad", "HC-SR04 Ultrasónico", sensores.get('ultrasonido', 'OFFLINE')),
        ("♨️ Detector Gas/Humo", "MQ-2 Digital", sensores.get('mq2', 'OFFLINE')),
        ("🎤 Micrófono Táctico", "INMP441 I2S Digital", sensores.get('mic_inmp441', 'OFFLINE'))
    ]
    
    for nombre, modelo, estado in sensores_info:
        conectado = False
        if isinstance(estado, dict):
            conectado = estado.get('conectado', False)
            if not conectado and "ONLINE" in str(estado): 
                conectado = True
        else:
            conectado = (str(estado) == "ONLINE")
        
        status_text = "🟢 ONLINE" if conectado else "🔴 OFFLINE"
        sensores_data.append({
            "Sensor": nombre,
            "Modelo": modelo,
            "Estado": status_text
        })
    
    df_sensores = pd.DataFrame(sensores_data)
    st.dataframe(df_sensores, use_container_width=True, hide_index=True)
    
    st.divider()
    
    # ==========================================
    # 📈 GRÁFICOS Y ANÁLISIS
    # ==========================================
    st.subheader("📈 Análisis Temporal")
    
    col_graf1, col_graf2 = st.columns(2)
    
    with col_graf1:
        st.markdown("#### 🌡️ Temperatura y Humedad")
        if len(estado_compartido.hist_temp) > 0:
            df_clima = pd.DataFrame({
                "Temperatura (°C)": list(estado_compartido.hist_temp),
                "Humedad (%)": list(estado_compartido.hist_hum)
            })
            # Se cambió area_chart por line_chart para ver las líneas separadas
            st.line_chart(df_clima, height=250, color=["#f97316", "#06b6d4"])
        else:
            st.info("Recopilando datos...")
    
    with col_graf2:
        st.markdown("#### 📏 Distancia Detectada")
        if len(estado_compartido.hist_distancia) > 0:
            df_dist = pd.DataFrame({
                "Distancia (cm)": list(estado_compartido.hist_distancia)
            })
            st.line_chart(df_dist, height=250, color="#ec4899")
            st.caption("🚨 Zona crítica: < 50cm | ⚠️ Zona advertencia: 50-100cm")
        else:
            st.info("Recopilando datos...")
    
    col_graf3, col_graf4 = st.columns(2)
    
    with col_graf3:
        st.markdown("#### ♨️ Nivel de Gas/Humo")
        if len(estado_compartido.hist_gas) > 0:
            df_gas = pd.DataFrame({
                "Estado Gas": list(estado_compartido.hist_gas)
            })
            st.line_chart(df_gas, height=250, color="#8b5cf6")
            st.caption("🔥 0 = Gas/Humo detectado | 1 = Aire limpio")
        else:
            st.info("Recopilando datos...")
    
    with col_graf4:
        st.markdown("#### ⚡ Evolución del Riesgo")
        if len(estado_compartido.hist_riesgo) > 0:
            df_riesgo = pd.DataFrame({
                "Score de Riesgo": list(estado_compartido.hist_riesgo)
            })
            st.area_chart(df_riesgo, height=250, color="#dc2626")
            st.caption("🟢 0-29: Seguro | 🟡 30-59: Precaución | 🔴 60-100: Crítico")
        else:
            st.info("Recopilando datos...")
    
    st.divider()
    
    # ==========================================
    # 🎧 AUDIO Y EVENTOS
    # ==========================================
    st.subheader("🎧 Monitoreo en Tiempo Real")
    
    col_audio, col_timeline = st.columns([1, 1])
    
    with col_audio:
        st.markdown("#### 🎧 Audio Táctico")
        
        if st.session_state.audio_local_activo:
            audio_data = estado_compartido.ultimo_audio_monitor
            if audio_data:
                ts = datetime.fromtimestamp(audio_data['timestamp']).strftime('%H:%M:%S')
                st.success(f"🔴 EN VIVO • Stream activo • {ts}", icon="📡")
                st.audio(base64.b64decode(audio_data['audio']), format='audio/wav', autoplay=True)
            else:
                st.warning("⏳ Esperando transmisión...")
        else:
            st.info("🔇 Audio desactivado\n\nActiva el toggle en el panel lateral para escuchar")
    
    with col_timeline:
        st.markdown("#### 📋 Timeline de Eventos")
        
        if estado_compartido.eventos_timeline:
            eventos_data = []
            for evento in list(estado_compartido.eventos_timeline)[:5]:
                ts_ev = datetime.fromtimestamp(evento['timestamp']).strftime('%H:%M:%S')
                eventos_data.append({
                    "Hora": ts_ev,
                    "Evento": f"{evento['icono']} {evento['titulo']}",
                    "Descripción": evento['descripcion']
                })
            
            df_eventos = pd.DataFrame(eventos_data)
            st.dataframe(df_eventos, use_container_width=True, hide_index=True)
        else:
            st.success("✅ Sin eventos recientes\n\nEl sistema está monitoreando...")
    
    st.divider()
    
    # ==========================================
    # 🤖 PANEL DE INTELIGENCIA ARTIFICIAL
    # ==========================================
    st.subheader("🤖 Análisis de Inteligencia Artificial")
    
    col_ia1, col_ia2 = st.columns([2, 1])
    
    with col_ia1:
        if prediccion['es_anomalia']:
            st.error(f"""
            ### 🧠 Motor de Detección de Anomalías
            
            **Estado:** {prediccion['mensaje']} {'⚠️' if prediccion['es_anomalia'] else '✅'}
            
            **Confianza:** {prediccion['confianza']}%
            
            ---
            
            **Estado del Modelo:** {'🟢 Entrenado' if estado_compartido.detector_ia.entrenado else '🟡 Calibrando'}
            
            **Muestras:** {len(estado_compartido.detector_ia.historial)}/50
            
            **Algoritmo:** Isolation Forest (Scikit-learn)
            """, icon="⚠️")
        else:
            st.success(f"""
            ### 🧠 Motor de Detección de Anomalías
            
            **Estado:** {prediccion['mensaje']} {'⚠️' if prediccion['es_anomalia'] else '✅'}
            
            **Confianza:** {prediccion['confianza']}%
            
            ---
            
            **Estado del Modelo:** {'🟢 Entrenado' if estado_compartido.detector_ia.entrenado else '🟡 Calibrando'}
            
            **Muestras:** {len(estado_compartido.detector_ia.historial)}/50
            
            **Algoritmo:** Isolation Forest (Scikit-learn)
            """, icon="✅")
    
    with col_ia2:
        st.markdown("#### 🎯 Factores de Riesgo")
        if riesgo['factores']:
            for factor in riesgo['factores']:
                st.markdown(f"• {factor}")
        else:
            st.success("✅ Sin factores de riesgo")
        
        st.divider()
        st.markdown("#### 📊 Resumen")
        st.metric("Score Total", f"{riesgo['score']}/100")
        st.metric("Nivel", riesgo['nivel'])

else:
    # ==========================================
    # 🔴 SISTEMA OFFLINE
    # ==========================================
    st.title("🔴 Sistema Desconectado")
    st.caption("No se reciben datos de la Raspberry Pi")
    
    col_off1, col_off2 = st.columns(2)
    col_off1.metric("Estado", "OFFLINE", "🔴")
    col_off2.metric("Última conexión", f"hace {int(tiempo_transcurrido)}s")
    
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
    

