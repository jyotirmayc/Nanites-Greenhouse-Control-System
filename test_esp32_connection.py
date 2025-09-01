#!/usr/bin/env python3
"""
Quick test to verify ESP32 telemetry is being received
"""
import paho.mqtt.client as mqtt
import json
import time

# MQTT Configuration
MQTT_BROKER = "broker.hivemq.com"
MQTT_PORT = 1883
MQTT_TOPIC = "greenhouse/A1/telemetry"

def on_connect(client, userdata, flags, rc):
    if rc == 0:
        print(f"✅ Connected to MQTT broker {MQTT_BROKER}:{MQTT_PORT}")
        client.subscribe(MQTT_TOPIC)
        print(f"✅ Subscribed to topic: {MQTT_TOPIC}")
    else:
        print(f"❌ Failed to connect to MQTT broker, return code {rc}")

def on_message(client, userdata, msg):
    try:
        payload = msg.payload.decode()
        data = json.loads(payload)
        print(f"📡 ESP32 Telemetry Received:")
        print(f"   📊 Data: {json.dumps(data, indent=2)}")
        print(f"   🕒 Timestamp: {data.get('ts')}")
        print(f"   🌡️  Temperature: {data.get('T')}°C")
        print(f"   💧 Humidity: {data.get('RH')}%")
        print(f"   🌱 Soil Moisture: {data.get('soil_theta')}")
        print(f"   💡 PPFD: {data.get('PPFD')}")
        print(f"   🌬️  CO2: {data.get('CO2')}")
        if 'ext_T' in data:
            print(f"   🌡️  External Temp: {data.get('ext_T')}°C")
        print("-" * 50)
    except Exception as e:
        print(f"❌ Error parsing message: {e}")

def main():
    print(f"🔄 Testing ESP32 Connection to {MQTT_BROKER}:{MQTT_PORT}")
    print(f"📡 Listening for telemetry on topic: {MQTT_TOPIC}")
    print("-" * 50)
    
    client = mqtt.Client()
    client.on_connect = on_connect
    client.on_message = on_message
    
    try:
        client.connect(MQTT_BROKER, MQTT_PORT, 60)
        client.loop_forever()
    except KeyboardInterrupt:
        print("\n🛑 Test stopped by user")
        client.disconnect()
    except Exception as e:
        print(f"❌ Connection error: {e}")

if __name__ == "__main__":
    main()
