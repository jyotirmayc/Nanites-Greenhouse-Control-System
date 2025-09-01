/* esp32_controller_wokwi.ino
   - Simulated Wi-Fi & MQTT for Wokwi
   - Publishes telemetry every 5s
   - Updates OLED display
*/

#include <WiFi.h>
#include <PubSubClient.h>
#include <Wire.h>
#include <Adafruit_GFX.h>
#include <Adafruit_SSD1306.h>
#include <DHT.h>
#include <ArduinoJson.h>

// CONFIG (Wokwi ignores SSID/PASS)
const char* WIFI_SSID = "Wokwi-GUEST";
const char* WIFI_PASS = "";
const char* MQTT_BROKER = "broker.hivemq.com";
const uint16_t MQTT_PORT = 1883;
const char* BAY = "A1";

// INTERVALS
const unsigned long TELEMETRY_INTERVAL_MS = 5000; // 5s
const unsigned long HEARTBEAT_INTERVAL_MS = 15000; // 15s

// OLED
#define SCREEN_WIDTH 128
#define SCREEN_HEIGHT 64
Adafruit_SSD1306 display(SCREEN_WIDTH, SCREEN_HEIGHT, &Wire, -1);

// Sensors (simulated with analogRead)
#define DHTPIN 4
#define DHTTYPE DHT22
DHT dht(DHTPIN, DHTTYPE);
#define SOIL_PIN 34
#define LDR_PIN 35
#define MQ2_PIN 32

// Actuators
#define FAN_PIN 25
#define PUMP_PIN 26
#define LED_PIN 27

// MQTT topics
String TOP_TELE = String("greenhouse/") + BAY + "/telemetry";
String TOP_STAT = String("greenhouse/") + BAY + "/status";
String TOP_CMD = String("greenhouse/") + BAY + "/cmd";

WiFiClient espClient;
PubSubClient mqtt(espClient);

// Actuator states
bool pump_state = false;
bool fan_state = false;

// Timing
unsigned long lastTeleMs = 0;
unsigned long lastHeartbeatMs = 0;

// Simulate soil volumetric water content
float analogToVWC(int raw) {
  float v = (4095.0 - raw) / 4095.0;
  if (v < 0) v = 0; if (v > 1) v = 1;
  return v;
}

// Connect to Wi-Fi (simulated)
void connectWiFi(){
  if (WiFi.status() == WL_CONNECTED) return;
  Serial.println("Simulated Wi-Fi connecting...");
  WiFi.begin(WIFI_SSID, WIFI_PASS);
  delay(500);
  WiFi.status() == WL_CONNECTED ? Serial.println("Wi-Fi connected (simulated).") : Serial.println("Wi-Fi failed (simulated).");
}

// MQTT callback
void mqttCallback(char* topic, byte* payload, unsigned int len) {
  Serial.print("Received MQTT: "); Serial.println(topic);
  
  if (String(topic) == TOP_CMD) {
    // Parse command JSON
    StaticJsonDocument<512> cmd;
    DeserializationError error = deserializeJson(cmd, payload, len);
    
    if (!error) {
      Serial.println("Processing command:");
      
      // Check if command has expired
      String expires_at = cmd["expires_at"];
      String cmd_id = cmd["cmd_id"];
      Serial.print("Command ID: "); Serial.println(cmd_id);
      
      // Process actions
      JsonObject actions = cmd["actions"];
      
      // Handle irrigation command
      if (actions.containsKey("irrigation")) {
        JsonObject irrig = actions["irrigation"];
        if (irrig["action"] == "on") {
          int duration = irrig["duration_s"];
          pump_state = true;
          digitalWrite(PUMP_PIN, HIGH);
          Serial.print("IRRIGATION ON for "); Serial.print(duration); Serial.println("s");
          // Note: In a real implementation, you'd use a timer to turn off after duration
        }
      }
      
      // Handle fan command
      if (actions.containsKey("fan")) {
        JsonObject fan_cmd = actions["fan"];
        if (fan_cmd["action"] == "set") {
          float duty = fan_cmd["duty"];
          fan_state = (duty > 0.5);
          digitalWrite(FAN_PIN, fan_state ? HIGH : LOW);
          Serial.print("FAN SET to duty: "); Serial.println(duty);
        }
      }
      
      // Handle safety mode
      if (actions.containsKey("safety")) {
        Serial.println("SAFETY MODE ACTIVATED");
        // Turn off pump, turn on fan
        pump_state = false;
        fan_state = true;
        digitalWrite(PUMP_PIN, LOW);
        digitalWrite(FAN_PIN, HIGH);
      }
    } else {
      Serial.print("JSON parse error: "); Serial.println(error.c_str());
    }
  }
}

// Connect to MQTT broker
void connectMQTT() {
  if (mqtt.connected()) return;
  mqtt.setServer(MQTT_BROKER, MQTT_PORT);
  mqtt.setCallback(mqttCallback);
  while (!mqtt.connected()) {
    String clientId = String("esp32-") + BAY + "-" + String(random(0xffff), HEX);
    if (mqtt.connect(clientId.c_str())) {
      Serial.println("MQTT connected!");
      // Subscribe to command topic
      mqtt.subscribe(TOP_CMD.c_str());
      Serial.print("Subscribed to: "); Serial.println(TOP_CMD);
    } else {
      Serial.print("MQTT failed, rc="); Serial.println(mqtt.state());
      delay(1000);
    }
  }
}

// Publish telemetry
void publishTelemetry(float T, float RH, float soil_vwc, float ppfd, float co2_proxy) {
  StaticJsonDocument<512> doc;
  doc["ts"] = String((unsigned long)(millis()/1000));
  doc["device_id"] = BAY;
  doc["T"] = T;
  doc["RH"] = RH;
  doc["soil_theta"] = soil_vwc;
  doc["PPFD"] = ppfd;
  doc["CO2"] = co2_proxy;
  
  char buf[512]; size_t n = serializeJson(doc, buf);
  mqtt.publish(TOP_TELE.c_str(), buf, n);
  Serial.println("Published telemetry:");
  Serial.println(buf);
}

// Publish status
void publishStatus() {
  StaticJsonDocument<256> s;
  s["ts"] = String((unsigned long)(millis()/1000));
  s["device_id"] = BAY;
  s["fan"] = fan_state;
  s["pump"] = pump_state;
  char b[256]; size_t n = serializeJson(s,b);
  mqtt.publish(TOP_STAT.c_str(), b, n);
}

void setup() {
  Serial.begin(115200);
  delay(100);
  dht.begin();
  display.begin(SSD1306_SWITCHCAPVCC, 0x3C);
  display.clearDisplay();
  pinMode(FAN_PIN, OUTPUT);
  pinMode(PUMP_PIN, OUTPUT);
  pinMode(LED_PIN, OUTPUT);

  connectWiFi();
  connectMQTT();
  lastTeleMs = millis();
  lastHeartbeatMs = millis();
}

void loop() {
  if (WiFi.status() != WL_CONNECTED) connectWiFi();
  if (!mqtt.connected()) connectMQTT();
  mqtt.loop();

  unsigned long now = millis();

  // Simulated sensor readings
  float temp = dht.readTemperature(); // 17-27 C
  float hum = dht.readHumidity(); // 30-70 %
  int soil_raw = analogRead(SOIL_PIN);
  int light_raw = analogRead(LDR_PIN);
  int mq2_raw = analogRead(MQ2_PIN);
  float soil_vwc = analogToVWC(soil_raw);
  float ppfd = (float)light_raw/4095.0 * 100.0;
  float co2_proxy = (float)mq2_raw/4095.0 * 1000.0;

  if (soil_vwc < 0.30) {  // less than 30% moisture
    pump_state = true;
    digitalWrite(PUMP_PIN, HIGH);
  } 
  else {
    pump_state = false;
    digitalWrite(PUMP_PIN, LOW);
  }

  if (temp > 28.0) {  // higher than 28 °C
    fan_state = true;
    digitalWrite(FAN_PIN, HIGH);
  } 
  else {
    fan_state = false;
    digitalWrite(FAN_PIN, LOW);
  }
  // Display
  display.clearDisplay();
  display.setTextSize(1); display.setTextColor(SSD1306_WHITE);
  display.setCursor(0,0); display.printf("T: %.1fC RH: %.0f%%", temp, hum);
  display.setCursor(0,10); display.printf("Soil: %.3f", soil_vwc);
  display.setCursor(0,20); display.printf("Fan:%s Pump:%s", fan_state?"ON":"OFF", pump_state?"ON":"OFF");
  display.display();

  // Publish telemetry
  if (now - lastTeleMs >= TELEMETRY_INTERVAL_MS) {
    lastTeleMs = now;
    publishTelemetry(temp, hum, soil_vwc, ppfd, co2_proxy);
  }

  // Publish status
  if (now - lastHeartbeatMs >= HEARTBEAT_INTERVAL_MS) {
    lastHeartbeatMs = now;
    publishStatus();
  }

  delay(200);
}
