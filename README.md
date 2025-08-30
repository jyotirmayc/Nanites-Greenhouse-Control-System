# IOTricity_Nanites
The IOT Project taken up by Nanites.

🌱 Greenhouse Control System

An IoT-powered Smart Greenhouse Control System that uses sensors and actuators to monitor and automate greenhouse conditions. This project integrates temperature, humidity, and soil moisture sensors with automated ventilation and irrigation systems, enhanced by AI-driven decision-making for optimal crop growth.

🚀 Features

📊 Real-time Monitoring
> Temperature, humidity, and soil moisture sensors provide live data.

🤖 AI-Powered Automation
> Smart algorithms adjust watering and ventilation automatically.
> Predictive AI models suggest the best conditions for specific crops.

💧 Automated Irrigation
> Watering system triggered when soil moisture is low.

🌬️ Smart Ventilation
> Fans or vents are activated when temperature/humidity exceed thresholds.

📱 Remote Access
> Web/mobile dashboard to view greenhouse conditions.
> Manual override option for farmers.

🛠️ Tech Stack
Hardware: Arduino / ESP32, DHT11/DHT22 (temperature & humidity), Soil Moisture Sensor, Relay Modules, Water Pump, Fans.

Software:
Backend: Node.js / Spring Boot
Frontend: React (for dashboard)
Database: Firebase / PostgreSQL
IoT Platform: MQTT / ThingsBoard

⚙️ System Architecture
Sensors collect environmental data.
Microcontroller (ESP32/Arduino) processes raw data.
IoT Gateway sends data to the cloud via MQTT.
AI Engine analyzes patterns and predicts required actions.
Actuators (pump, fan, vents) execute control decisions.
Dashboard (Web/Mobile) displays data & allows manual override.
AI Integration
Decision Support: AI suggests irrigation/ventilation timing based on weather forecasts & crop type.
Adaptive Learning: System improves with usage by analyzing past patterns.
Optimization: Reduces water/electricity usage while maximizing crop health.

ESP32 = Edge controller → real-time sensing & actuator driving.
Raspberry Pi / Jetson Nano / Cloud = AI layer → heavy ML tasks (yield prediction, anomaly detection, vision).

| Responsibility                                     | Hardware (sensors & actuators)                                                                                                                                                                  | Smart Models (AI/Control Algorithms)                                                                                                                                                                                |
| -------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Climate Control (Temp, Humidity, CO₂, Airflow)** | - Temp/Humidity: **BME280 / SHT31 / DHT22** <br> - CO₂: **SCD30 / MH-Z19B** <br> - Ventilation fans + MOSFET/relay <br> - Heater (PTC, resistive mats) <br> - Misters/humidifiers/dehumidifiers | - **PID control** for temp & humidity <br> - **Model Predictive Control (MPC)** with weather forecast <br> - **Adaptive VPD control** (vapor pressure deficit) <br> - **Anomaly detection** for stuck fans/heaters  |
| **Irrigation & Water Management**                  | - Soil moisture: **capacitive probes (temp compensated)** <br> - Flow sensor: **YF-S201** <br> - Solenoid valves, DC pumps <br> - Water level float sensors                                     | - **ET₀-based scheduling** (FAO-56 Penman-Monteith) <br> - **Hybrid threshold + ET₀** irrigation <br> - **Random Forest regression** for irrigation prediction <br> - **Nutrient fertigation model** (optional)     |
| **Lighting Control**                               | - Light sensor: **BH1750 / TSL2591** (budget) or **PAR quantum sensor** (Apogee SQ-500) <br> - LED grow lights w/ PWM dimming driver                                                            | - **DLI (Daily Light Integral)** scheduling <br> - **Energy optimization model** (balance natural + artificial light) <br> - Crop-stage-specific light schedules                                                    |
| **CO₂ Enrichment**                                 | - NDIR CO₂ sensor (SCD30) <br> - CO₂ solenoid valves                                                                                                                                            | - Maintain setpoints w/ hysteresis <br> - **Feedforward model** (lockout when vents open) <br> - Crop-growth/yield correlation models                                                                               |
| **Crop Growth Monitoring & Yield Prediction**      | - ESP32-CAM / Pi Camera <br> - Ultrasonic sensor for plant height <br> - Weight sensors for biomass                                                                                             | - **Computer Vision (YOLO, CNNs)** for leaf/fruit detection, ripeness <br> - **Growth regression models** (using DLI, degree-days, irrigation, CO₂) <br> - **Yield forecasting** (Gradient Boosting, Random Forest) |
| **User Alerts & Interface**                        | - ESP32 Wi-Fi / LoRa nodes <br> - Cloud dashboard (Adafruit IO, ThingsBoard, Grafana) <br> - Mobile app/web UI                                                                                  | - **Alert prioritization model** (classify urgency of events) <br> - **Predictive harvest readiness alerts** <br> - **Fault detection model** (sensor drift, actuator failure)                                      |
| **IoT Connectivity & Edge Control**                | - ESP32 (Wi-Fi for bay-level control) <br> - LoRaWAN nodes + gateway for multi-bay farm <br> - MQTT broker (Mosquitto / AWS IoT / Azure IoT)                                                    | - **Local fallback control** if cloud is down <br> - **Bayesian optimization** for tuning setpoints <br> - **Anomaly detection** (Isolation Forest, clustering)                                                     |









📌 Future Enhancements

Integration with weather APIs for predictive control.

Advanced computer vision for plant health monitoring.

Voice assistant support for farmers.

Solar-powered automation.
