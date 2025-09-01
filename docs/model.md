# IOTricity AI Pipeline: Technical Documentation

## 🧠 Machine Learning Architecture

### Data Generation & Preprocessing
- **generate_synthetic.py**: Generates realistic greenhouse sensor data for 7 days at 10-minute intervals, simulating temperature, humidity, light, CO₂, soil moisture, and irrigation events. Uses `config.yaml` for output paths and saves to `AI/data/synthetic_greenhouse_7days_10min.csv`.

### Model Training Pipeline
- **train_irrigation.py**: Loads synthetic data, engineers temporal features (lags, rolling averages, hour-of-day), trains Random Forest regressor to predict soil moisture 6 hours ahead. Saves model to `models/irrigation_rf.pkl` with metadata in `irrigation_rf_meta.json`.
- **train_anomaly.py**: Trains Isolation Forest model for anomaly detection using features: Temperature, Humidity, Soil Theta, PPFD, CO₂. Saves to `models/anomaly_iforest.pkl` with metadata.

### Real-Time Inference & Control
- **cloud_controller.py**: Cloud-deployed MQTT service that loads trained models, processes real-time telemetry from ESP32 sensors, predicts soil moisture needs, detects anomalies, and publishes irrigation/climate control commands back to hardware.

### Visualization & Monitoring  
- **flask_dashboard.py**: Modern web interface using Flask + Socket.IO for real-time data visualization. Features beautiful responsive design with live sensor readings, AI command monitoring, and connection status indicators.

### Utility Functions
- **utils.py**: Helper functions for model saving/loading, path resolution, and configuration management.

## 🔄 Production Workflow

1. **Data Generation**: Generate synthetic training data
2. **Model Training**: Train irrigation prediction + anomaly detection models  
3. **Cloud Deployment**: Deploy Docker container with AI controller + dashboard
4. **Hardware Connection**: ESP32 sensors → MQTT → Cloud AI → Commands → ESP32 actuators
5. **Real-time Monitoring**: Flask dashboard displays live data + AI decisions

## 📁 Updated File Structure
- `AI/data/`: Synthetic training datasets
- `AI/models/`: Trained ML models (.pkl) + metadata (.json)
- `AI/src/`: Core ML pipeline + Flask dashboard
- `Hardware/Arduino/`: ESP32 sensor/actuator code
- `Dockerfile`: Production cloud deployment configuration

# IOTricity Setup & Deployment Guide

## 🚀 Local Development Setup (Windows PowerShell)

1. **Create and activate Python virtual environment:**
   ```powershell
   python -m venv .venv
   .venv\Scripts\Activate.ps1
   ```

2. **Install dependencies:**
   ```powershell
   pip install -r requirements.txt
   ```

3. **Generate synthetic training data:**
   ```powershell
   cd AI/src
   python generate_synthetic.py
   ```

4. **Train AI models:**
   ```powershell
   python train_irrigation.py
   python train_anomaly.py
   ```

5. **Start cloud AI controller:**
   ```powershell
   python cloud_controller.py
   ```

6. **Launch beautiful dashboard:**
   ```powershell
   python flask_dashboard.py
   # Dashboard available at: http://localhost:5000
   ```

## 🐳 Production Cloud Deployment

1. **Build Docker image:**
   ```bash
   docker build -t iotricity-ai .
   ```

2. **Deploy to cloud platform:**
   ```bash
   # Google Cloud Run, AWS ECS, Azure Container Instances, etc.
   docker run -p 8080:8080 iotricity-ai
   ```

3. **Connect ESP32 hardware:**
   - Flash `Hardware/Arduino/esp32_code.ino` to ESP32
   - Configure WiFi and MQTT broker settings
   - Hardware automatically connects to cloud AI system

---

## 🔧 Architecture Highlights

**Real-time Data Flow**: ESP32 Sensors → MQTT (HiveMQ) → Cloud AI → Flask Dashboard → WebSocket → Browser

**AI Models**: RandomForest (irrigation prediction) + IsolationForest (anomaly detection)

**Production Features**: Docker deployment, health checks, auto-scaling, real-time WebSocket updates

*This system is production-ready for commercial greenhouse deployment.* ✅