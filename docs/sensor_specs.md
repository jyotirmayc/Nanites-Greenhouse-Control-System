# Greenhouse Sensor Hardware Specifications

This document provides the details and specifications of the sensors used in the greenhouse simulation project. The sensors are used for monitoring CO₂ levels, soil moisture, sunlight, temperature, and humidity.

---

## 1. **MQ2 Gas Sensor (CO₂ Sensor in Simulation)**

**Purpose:** Detects the presence of gases such as CO₂, LPG, methane, and smoke.  

**Specifications:**
- **Type:** Gas sensor (analog/digital output)
- **Operating Voltage:** 5V DC
- **Detectable Gases:** LPG, methane, smoke, CO₂ (simulated)
- **Output:** Analog and digital (digital pin triggers on threshold)
- **Sensitivity Adjustment:** Via onboard potentiometer
- **Response Time:** < 10 seconds
- **Temperature Operating Range:** -20°C to 50°C
- **Notes:** In simulation, used to represent CO₂ levels.

---

## 2. **Potentiometer (Soil Moisture Sensor in Simulation)**

**Purpose:** Acts as a simulated soil moisture sensor by providing variable analog input.  

**Specifications:**
- **Type:** Rotary potentiometer (variable resistor)
- **Operating Voltage:** 5V DC
- **Output Range:** 0 – 5V analog
- **Resistance:** 10kΩ typical
- **Application:** Turn knob to simulate wet or dry soil conditions
- **Notes:** Can replace real soil moisture sensor in simulation.

---

## 3. **LDR (Sunlight Sensor)**

**Purpose:** Measures ambient light intensity to monitor sunlight for plants.  

**Specifications:**
- **Type:** Photoresistor (Light Dependent Resistor)
- **Resistance Range:** ~10Ω (bright light) – 1MΩ (dark)
- **Operating Voltage:** 3.3V – 5V DC
- **Response Time:** ~100ms
- **Placement:** Place in sunlight-exposed area of greenhouse
- **Output:** Analog signal proportional to light intensity

---

## 4. **DHT22 (Temperature and Humidity Sensor)**

**Purpose:** Monitors temperature and relative humidity in the greenhouse.  

**Specifications:**
- **Type:** Digital temperature & humidity sensor
- **Temperature Range:** -40°C to 80°C
- **Temperature Accuracy:** ±0.5°C
- **Humidity Range:** 0% – 100% RH
- **Humidity Accuracy:** ±2% RH
- **Operating Voltage:** 3.3V – 6V DC
- **Signal Type:** Digital (single-wire data interface)
- **Response Time:** 2 seconds typical
- **Notes:** Provides reliable environmental monitoring for plant health.

---

## **Summary Table of Sensors**

| Sensor       | Purpose                           | Output      | Voltage   | Range / Notes                 |
|-------------|-----------------------------------|------------|----------|-------------------------------|
| MQ2         | CO₂ / Gas Detection (simulated)  | Analog/Digital | 5V       | Detects CO₂, LPG, methane    |
| Potentiometer | Soil Moisture Simulation         | Analog      | 5V       | Variable analog value        |
| LDR         | Sunlight Measurement             | Analog      | 3.3V–5V  | Light-dependent resistance   |
| DHT22       | Temperature & Humidity           | Digital     | 3.3V–6V  | Accurate temp & RH readings  |

---

**Note:** In this project, some sensors are used in simulation mode. For real-world implementation, replace the potentiometer with an actual soil moisture sensor, and MQ2 should be calibrated for CO₂ detection.

