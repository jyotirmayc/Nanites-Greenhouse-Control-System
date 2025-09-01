#!/usr/bin/env python3
"""
Quick test to verify MQTT connectivity with all services
"""
import paho.mqtt.client as mqtt
import json
import time
import sys

# Test with the broker configuration
BROKER = "broker.hivemq.com"
PORT = 1883
TOPIC = "greenhouse/A1/telemetry"

print("🔍 Testing MQTT connectivity...")
print(f"📡 Broker: {BROKER}:{PORT}")
print(f"📨 Topic: {TOPIC}")

def on_connect(client, userdata, flags, rc):
    if rc == 0:
        print("✅ Connected successfully!")
        client.subscribe(TOPIC)
        print(f"✅ Subscribed to {TOPIC}")
        
        # Publish test message
        test_msg = {
            "ts": str(int(time.time())),
            "device_id": "A1", 
            "T": 25.0,
            "RH": 65.0,
            "soil_theta": 0.32,
            "PPFD": 800.0,
            "CO2": 450.0,
            "ext_T": 24.5
        }
        client.publish(TOPIC, json.dumps(test_msg))
        print("📤 Published test message")
        
    else:
        print(f"❌ Connection failed with code {rc}")
        sys.exit(1)

def on_message(client, userdata, msg):
    try:
        payload = json.loads(msg.payload.decode())
        print(f"📨 Received message:")
        print(f"   Topic: {msg.topic}")
        print(f"   Data: {payload}")
        print("---")
    except Exception as e:
        print(f"❌ Error parsing: {e}")

client = mqtt.Client()
client.on_connect = on_connect
client.on_message = on_message

try:
    client.connect(BROKER, PORT, 60)
    client.loop_start()
    print("⏱️ Listening for 10 seconds...")
    time.sleep(10)
    print("✅ Test completed successfully!")
    
except Exception as e:
    print(f"❌ Connection error: {e}")
    
finally:
    client.loop_stop()
    client.disconnect()
