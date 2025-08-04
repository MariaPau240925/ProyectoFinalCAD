#include <WiFi.h>
#include <DHT.h>
#include <HTTPClient.h>
#include <ArduinoJson.h>

// Pines de sensores
#define DHTPIN 15
#define DHTTYPE DHT11
#define LM35PIN 33

DHT dht(DHTPIN, DHTTYPE);

// Red WiFi
const char* ssid = "Majito";
const char* password = "123456789";

// Dirección de tu servidor Python (PC)
const char* serverUrl = "http://172.20.10.10:5000/data";  

unsigned long lastReadMillis = 0;
const long interval = 2000;  // 2 segundos

void setup() {
  Serial.begin(9600);
  dht.begin();

  WiFi.begin(ssid, password);
  Serial.print("Conectando a WiFi");

  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }

  Serial.println("\nConectado a WiFi");
  Serial.print("Dirección IP: ");
  Serial.println(WiFi.localIP());

  pinMode(LM35PIN, INPUT);
}

void loop() {
  unsigned long currentMillis = millis();

  if (currentMillis - lastReadMillis >= interval) {
    lastReadMillis = currentMillis;

    // Lectura de sensores
    float h = dht.readHumidity();
    float t_dht = dht.readTemperature();

    int raw_adc = analogRead(LM35PIN);
    float voltage = raw_adc * (3.3 / 4095.0);
    float t_lm35 = voltage * 100.0;

    // Impresion de lecturas en Serial
    Serial.println("=== Lecturas sensores ===");
    if (isnan(h) || isnan(t_dht)) {
      Serial.println("Error al leer DHT11");
    } else {
      Serial.print("DHT11 Temperatura: ");
      Serial.print(t_dht);
      Serial.println(" °C");
      Serial.print("DHT11 Humedad: ");
      Serial.print(h);
      Serial.println(" %");
    }
    Serial.print("LM35 Temperatura: ");
    Serial.print(t_lm35);
    Serial.println(" °C");

    // Creacion de JSON
    StaticJsonDocument<256> doc;
    doc["timestamp"] = millis();

    JsonObject dht11 = doc.createNestedObject("DHT11");
    dht11["temp"] = t_dht;
    dht11["hum"] = h;

    JsonObject lm35 = doc.createNestedObject("LM35");
    lm35["temp"] = t_lm35;

    String jsonStr;
    serializeJson(doc, jsonStr);

    // Envio por HTTP POST
    if (WiFi.status() == WL_CONNECTED) {
      HTTPClient http;
      http.begin(serverUrl);
      http.addHeader("Content-Type", "application/json");

      int httpResponseCode = http.POST(jsonStr);
      if (httpResponseCode > 0) {
        Serial.println("Datos enviados:");
        Serial.println(jsonStr);
      } else {
        Serial.print("Error HTTP: ");
        Serial.println(httpResponseCode);
      }
      http.end();
    } else {
      Serial.println("WiFi no conectado");
    }

    Serial.println();
  }
}