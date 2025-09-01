# Use Python 3.9 slim image
FROM python:3.9-slim

# Set working directory
WORKDIR /app

# Copy requirements first (for better Docker layer caching)
COPY requirements.txt .

# Install Python dependencies and curl for health checks
RUN apt-get update && apt-get install -y curl && rm -rf /var/lib/apt/lists/* \
    && pip install --no-cache-dir -r requirements.txt

# Copy only essential AI components for cloud deployment
COPY AI/config.yaml ./AI/
COPY AI/data/ ./AI/data/
COPY AI/models/ ./AI/models/

# Copy only essential source files (exclude local/demo files)
COPY AI/src/cloud_controller.py ./AI/src/
COPY AI/src/utils.py ./AI/src/
COPY AI/src/streamlit_dashboard.py ./AI/src/
COPY AI/src/generate_synthetic.py ./AI/src/
COPY AI/src/train_irrigation.py ./AI/src/
COPY AI/src/train_anomaly.py ./AI/src/

# Copy additional data if present
COPY data/ ./data/ 

# Set environment variables for cloud deployment
ENV PYTHONPATH=/app
ENV MQTT_BROKER=broker.hivemq.com
ENV MQTT_PORT=1883
ENV PYTHONUNBUFFERED=1

# Expose port for Cloud Run
EXPOSE 8080

# Create startup script that handles the proper AI workflow
RUN echo '#!/bin/bash\n\
set -e\n\
cd /app\n\
echo "🚀 Starting IoTricity AI Service..."\n\
\n\
# Ensure directories exist\n\
mkdir -p AI/models AI/data AI/logs\n\
\n\
# Step 1: Generate synthetic data if not present\n\
if [ ! -f "AI/data/synthetic_greenhouse_7days_10min.csv" ]; then\n\
  echo "📊 Generating synthetic training data..."\n\
  cd AI/src && python generate_synthetic.py && cd /app\n\
fi\n\
\n\
# Step 2: Train models if not present\n\
if [ ! -f "AI/models/irrigation_rf.pkl" ]; then\n\
  echo "🧠 Training irrigation model..."\n\
  cd AI/src && python train_irrigation.py && cd /app\n\
fi\n\
\n\
if [ ! -f "AI/models/anomaly_iforest.pkl" ]; then\n\
  echo "🔍 Training anomaly detection model..."\n\
  cd AI/src && python train_anomaly.py && cd /app\n\
fi\n\
\n\
echo "✅ Models ready!"\n\
\n\
# Step 3: Start AI services\n\
echo "🤖 Starting cloud controller (AI brain)..."\n\
cd AI/src && python cloud_controller.py &\n\
CONTROLLER_PID=$!\n\
\n\
# Wait a moment for controller to initialize\n\
sleep 3\n\
\n\
echo "📊 Starting Streamlit dashboard..."\n\
# Start Streamlit dashboard (this runs in foreground)\n\
streamlit run streamlit_dashboard.py --server.port=8080 --server.address=0.0.0.0 --server.headless=true\n\
' > start.sh

RUN chmod +x start.sh

# Health check for Cloud Run
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s \
  CMD curl -f http://localhost:8080 || exit 1

# Run the startup script
CMD ["./start.sh"]
