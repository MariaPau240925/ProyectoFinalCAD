from flask import Flask, request, jsonify
from datetime import datetime
import json
import smtplib
import requests  
from email.mime.text import MIMEText
from influxdb_client import InfluxDBClient, Point
from influxdb_client.client.write_api import SYNCHRONOUS
from influxdb_client.rest import ApiException
import os
import dateutil.parser  

# INFLUXDB
influx_url = "http://localhost:8086"
influx_token = "fkS22nKqHX3bOdejM1b20BzIWysD-8ZDD0KcW7QKOmPfhSinENshcKFeJ3rvhznmadeh5nGTB-QjSqNTHWYqaA=="
influx_org = "Comunicaciones AD"
influx_bucket = "Proyecto CAD"

# SMTP 
EMAIL_USER = "mariajosepaucarochoa@gmail.com"
EMAIL_PASS = "pnkxvqbltlrehtih"
EMAIL_TO = "jorgederek12@gmail.com"

# TELEGRAM
TELEGRAM_TOKEN = "8388557527:AAGl1rJ5K_6bULUOMR8C_juPie9VRH3r8Nk"
TELEGRAM_CHAT_ID = "1849231301"

# ARCHIVO PARA GUARDAR LOS DATOS
FILE_NAME = "datos.json"

app = Flask(__name__)
influx_client = InfluxDBClient(url=influx_url, token=influx_token, org=influx_org)
write_api = influx_client.write_api(write_options=SYNCHRONOUS)

# FUNCIONES PARA ENVIAR ALERTAS
def enviar_telegram(mensaje):
    try:
        url = f'https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage'
        payload = {'chat_id': TELEGRAM_CHAT_ID, 'text': mensaje}
        response = requests.post(url, data=payload)
        if response.status_code == 200:
            print("Mensaje de Telegram enviado")
        else:
            print("Error al enviar mensaje de Telegram:", response.text)
    except Exception as e:
        print(f"Excepción al enviar Telegram: {e}")

def enviar_correo(mensaje):
    msg = MIMEText(mensaje)
    msg['Subject'] = 'Alerta de temperatura ESP32'
    msg['From'] = EMAIL_USER
    msg['To'] = EMAIL_TO
    try:
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
            server.login(EMAIL_USER, EMAIL_PASS)
            server.send_message(msg)
            print("Correo de alerta enviado")
    except Exception as e:
        print(f"Error al enviar correo: {e}")

# GUARDAR DATOS EN INFLUXDB
def guardar_en_influxdb(datos):
    timestamp = datetime.utcnow()
    try:
        if "DHT11" in datos:
            dht = datos["DHT11"]
            point = (
                Point("sensor_dht11")
                .tag("device", "esp32")
                .field("temperature", float(dht["temp"]))
                .field("humidity", float(dht["hum"]))
                .time(timestamp)
            )
            write_api.write(bucket=influx_bucket, org=influx_org, record=point)
            print("Datos DHT11 enviados a InfluxDB")
        if "LM35" in datos:
            lm = datos["LM35"]
            point = (
                Point("sensor_lm35")
                .tag("device", "esp32")
                .field("temperature", float(lm["temp"]))
                .time(timestamp)
            )
            write_api.write(bucket=influx_bucket, org=influx_org, record=point)
            print("Datos LM35 enviados a InfluxDB")
    except ApiException as e:
        print(f"Error InfluxDB: {e}")
    except Exception as e:
        print(f"Error inesperado InfluxDB: {e}")

# RUTA PARA RECIBIR DATOS DEL ESP32
@app.route('/data', methods=['POST'])
def recibir_datos():
    try:
        datos = request.get_json()
        print("Datos recibidos:")
        print(json.dumps(datos, indent=2))

        datos['received_at'] = datetime.utcnow().isoformat() + 'Z'

        if os.path.exists(FILE_NAME):
            with open(FILE_NAME, "r") as f:
                try:
                    data_list = json.load(f)
                    if not isinstance(data_list, list):
                        data_list = []
                except json.JSONDecodeError:
                    data_list = []
        else:
            data_list = []

        data_list.append(datos)

        with open(FILE_NAME, "w") as f:
            json.dump(data_list, f, indent=4)

        print(f"Datos guardados en {FILE_NAME}")

        # Guardar datos en InfluxDB
        guardar_en_influxdb(datos)

        # Alertas si temperatura aumenta
        alerta = False
        mensaje = "Temperatura elevada detectada:\n"
        if datos.get("DHT11", {}).get("temp", 0) > 23:
            alerta = True
            mensaje += f"- DHT11: {datos['DHT11']['temp']} °C\n"
            print("Alerta: DHT11 superó el umbral.")
        if datos.get("LM35", {}).get("temp", 0) > 20:
            alerta = True
            mensaje += f"- LM35: {datos['LM35']['temp']} °C\n"
            print("Alerta: LM35 superó el umbral")

        if alerta:
            print("Activando notificaciones...")
            enviar_correo(mensaje)
            enviar_telegram(mensaje)
        else:
            print("Temperaturas normales.")

        return jsonify({"status": "OK", "message": "Datos procesados"}), 200

    except Exception as e:
        print(f"Error al procesar datos: {e}")
        return jsonify({"status": "ERROR", "message": str(e)}), 400

# CONEXION DE JSON API PARA GRAFANA
@app.route('/jsonapi', methods=['GET'])
def jsonapi():
    try:
        with open(FILE_NAME, "r") as f:
            registros = json.load(f)
    except Exception:
        return jsonify([])

    series_dht_temp = {"target": "DHT11_temperature", "datapoints": []}
    series_dht_hum = {"target": "DHT11_humidity", "datapoints": []}
    series_lm35_temp = {"target": "LM35_temperature", "datapoints": []}

    for reg in registros:
        try:
            ts = dateutil.parser.isoparse(reg["received_at"])
            epoch_ms = int(ts.timestamp() * 1000)

            if "DHT11" in reg:
                if "temp" in reg["DHT11"]:
                    series_dht_temp["datapoints"].append([float(reg["DHT11"]["temp"]), epoch_ms])
                if "hum" in reg["DHT11"]:
                    series_dht_hum["datapoints"].append([float(reg["DHT11"]["hum"]), epoch_ms])

            if "LM35" in reg and "temp" in reg["LM35"]:
                series_lm35_temp["datapoints"].append([float(reg["LM35"]["temp"]), epoch_ms])
        except Exception as e:
            print("Error en registro:", e)

    return jsonify([series_dht_temp, series_dht_hum, series_lm35_temp])

# EJECUCIÓN DEL CODIGO
if __name__ == '__main__':
    app.run(host="0.0.0.0", port=5000)
