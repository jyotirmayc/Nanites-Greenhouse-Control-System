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
COPY AI/config.yaml ./AI/config.yaml
COPY AI/data/ ./AI/data/

# Don't copy existing models - we'll retrain them with compatible versions
# Copy only essential source files (exclude local/demo files)
COPY AI/src/cloud_controller.py ./AI/src/
COPY AI/src/utils.py ./AI/src/
COPY AI/src/flask_dashboard.py ./AI/src/
COPY AI/src/generate_synthetic.py ./AI/src/
COPY AI/src/train_irrigation.py ./AI/src/
COPY AI/src/train_anomaly.py ./AI/src/ 

# Set environment variables for cloud deployment
ENV PYTHONPATH=/app
ENV MQTT_BROKER=broker.hivemq.com
ENV MQTT_PORT=1883
ENV PYTHONUNBUFFERED=1

# Expose port for Cloud Run (Flask dashboard)
EXPOSE 8080

# Create startup script that handles the proper AI workflow
RUN echo '#!/bin/bash\n\
set -e\n\
echo "🚀 Starting IoTricity AI Service..."\n\
echo "📁 Current directory: $(pwd)"\n\
echo "📁 Full directory structure:"\n\
find /app -type f -name "*.py" -o -name "*.yaml" -o -name "*.csv" | head -20\n\
\n\
# Ensure directories exist\n\
mkdir -p AI/models AI/data AI/logs\n\
echo "📁 Created directories: AI/models AI/data AI/logs"\n\
\n\
# Change to AI/src directory for proper relative paths\n\
cd /app/AI/src\n\
echo "📁 Changed to: $(pwd)"\n\
echo "📁 Contents of current directory:"\n\
ls -la\n\
echo "📁 Contents of ../config.yaml location:"\n\
ls -la ../\n\
\n\
# Step 1: Generate synthetic data\n\
echo "📊 Generating synthetic training data..."\n\
python generate_synthetic.py\n\
echo "📊 Data generation completed"\n\
\n\
# Verify data file exists\n\
if [ -f "../data/synthetic_greenhouse_7days_10min.csv" ]; then\n\
  echo "✅ Data file found: ../data/synthetic_greenhouse_7days_10min.csv"\n\
  wc -l ../data/synthetic_greenhouse_7days_10min.csv\n\
else\n\
  echo "❌ Data file not found, checking all CSV files in container..."\n\
  find /app -name "*.csv" -type f\n\
  exit 1\n\
fi\n\
\n\
# Step 2: Train models\n\
echo "🧠 Training irrigation model..."\n\
python train_irrigation.py\n\
echo "✅ Irrigation model trained"\n\
\n\
echo "🔍 Training anomaly detection model..."\n\
python train_anomaly.py\n\
echo "✅ Anomaly model trained"\n\
\n\
echo "✅ All models ready!"\n\
ls -la ../models/\n\
\n\
# Step 3: Start AI services\n\
echo "🤖 Starting cloud controller (AI brain)..."\n\
python cloud_controller.py &\n\
CONTROLLER_PID=$!\n\
echo "📝 Controller PID: $CONTROLLER_PID"\n\
\n\
# Wait a moment for controller to initialize\n\
sleep 5\n\
\n\
echo "🌐 Starting Flask dashboard on port 8080..."\n\
# Start Flask dashboard with proper production setup\n\
export FLASK_ENV=production\n\
export PORT=8080\n\
exec python flask_dashboard.py\n\
' > start.sh

RUN chmod +x start.sh

# Health check for Cloud Run
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s \
  CMD curl -f http://localhost:8080 || exit 1

# Run the startup script
CMD ["./start.sh"]
