#!/usr/bin/env python3
"""
Flask-based IOTricity Dashboard
Real-time ESP32 data display without threading issues
"""
from flask import Flask, render_template_string, jsonify
from flask_socketio import SocketIO, emit
import paho.mqtt.client as mqtt
import json
import logging
from datetime import datetime
import threading
import time
import os

# Configuration
MQTT_BROKER = "broker.hivemq.com"
MQTT_PORT = 1883
TELEMETRY_TOPIC = "greenhouse/A1/telemetry"
COMMAND_TOPIC = "greenhouse/A1/cmd"
FLASK_PORT = int(os.environ.get('PORT', 5000))

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Flask app with Socket.IO
app = Flask(__name__)
app.config['SECRET_KEY'] = 'iotricity_secret'
socketio = SocketIO(app, cors_allowed_origins="*")

# Global state
latest_data = {
    'device_id': 'A1',
    'temperature': 'N/A',
    'humidity': 'N/A',
    'soil_moisture': 'N/A',
    'light_intensity': 'N/A',
    'co2_level': 'N/A',
    'last_update': 'Never',
    'connected': False,
    'commands': [],
    'data_count': 0
}

# HTML Template with modern, beautiful design
HTML_TEMPLATE = '''
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>IOTricity - Smart Greenhouse Monitor</title>
    <script src="https://cdnjs.cloudflare.com/ajax/libs/socket.io/4.7.2/socket.io.js"></script>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap" rel="stylesheet">
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        
        body {
            font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            color: #2d3748;
            overflow-x: hidden;
        }
        
        .particles {
            position: fixed;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            pointer-events: none;
            z-index: -1;
        }
        
        .particle {
            position: absolute;
            background: rgba(255, 255, 255, 0.1);
            border-radius: 50%;
            animation: float 6s ease-in-out infinite;
        }
        
        @keyframes float {
            0%, 100% { transform: translateY(0px) rotate(0deg); opacity: 1; }
            50% { transform: translateY(-20px) rotate(180deg); opacity: 0.8; }
        }
        
        .container {
            max-width: 1400px;
            margin: 0 auto;
            padding: 20px;
        }
        
        .header {
            text-align: center;
            margin-bottom: 40px;
            padding: 30px 20px;
            background: rgba(255, 255, 255, 0.95);
            backdrop-filter: blur(10px);
            border-radius: 20px;
            box-shadow: 0 20px 40px rgba(0,0,0,0.1);
            border: 1px solid rgba(255, 255, 255, 0.2);
        }
        
        .header h1 {
            font-size: 3.5em;
            font-weight: 700;
            background: linear-gradient(135deg, #667eea, #764ba2);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            margin-bottom: 10px;
        }
        
        .header h3 {
            font-size: 1.3em;
            color: #718096;
            font-weight: 400;
        }
        
        .status {
            padding: 15px 30px;
            border-radius: 50px;
            text-align: center;
            font-weight: 600;
            margin-bottom: 40px;
            font-size: 1.1em;
            transition: all 0.3s ease;
            backdrop-filter: blur(10px);
        }
        
        .connected { 
            background: linear-gradient(135deg, #10b981, #059669);
            color: white;
            box-shadow: 0 10px 30px rgba(16, 185, 129, 0.3);
        }
        
        .disconnected { 
            background: linear-gradient(135deg, #ef4444, #dc2626);
            color: white;
            box-shadow: 0 10px 30px rgba(239, 68, 68, 0.3);
        }
        
        .dashboard {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
            gap: 30px;
            margin-bottom: 40px;
        }
        
        .metric-card {
            background: rgba(255, 255, 255, 0.95);
            backdrop-filter: blur(15px);
            padding: 30px;
            border-radius: 20px;
            box-shadow: 0 20px 40px rgba(0,0,0,0.1);
            text-align: center;
            position: relative;
            overflow: hidden;
            transition: transform 0.3s ease, box-shadow 0.3s ease;
            border: 1px solid rgba(255, 255, 255, 0.2);
        }
        
        .metric-card:hover {
            transform: translateY(-10px);
            box-shadow: 0 30px 60px rgba(0,0,0,0.2);
        }
        
        .metric-card::before {
            content: '';
            position: absolute;
            top: 0;
            left: 0;
            right: 0;
            height: 4px;
            background: var(--accent-color);
            border-radius: 20px 20px 0 0;
        }
        
        .metric-icon {
            font-size: 3em;
            margin-bottom: 15px;
            color: var(--accent-color);
        }
        
        .metric-value {
            font-size: 2.8em;
            font-weight: 700;
            margin: 15px 0;
            color: #2d3748;
            font-variant-numeric: tabular-nums;
        }
        
        .metric-label {
            color: #718096;
            font-size: 1em;
            font-weight: 500;
            text-transform: uppercase;
            letter-spacing: 1px;
        }
        
        .metric-unit {
            color: #a0aec0;
            font-size: 0.9em;
            font-weight: 400;
            margin-top: 5px;
        }
        
        .temperature { --accent-color: #ef4444; }
        .humidity { --accent-color: #3b82f6; }
        .soil { --accent-color: #8b5cf6; }
        .light { --accent-color: #f59e0b; }
        .co2 { --accent-color: #10b981; }
        
        .commands-section {
            background: rgba(255, 255, 255, 0.95);
            backdrop-filter: blur(15px);
            padding: 30px;
            border-radius: 20px;
            box-shadow: 0 20px 40px rgba(0,0,0,0.1);
            border: 1px solid rgba(255, 255, 255, 0.2);
            margin-bottom: 40px;
        }
        
        .commands-header {
            display: flex;
            align-items: center;
            margin-bottom: 25px;
            font-size: 1.4em;
            font-weight: 600;
            color: #2d3748;
        }
        
        .commands-header i {
            margin-right: 12px;
            color: #6366f1;
        }
        
        .commands-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 15px;
            margin-bottom: 25px;
        }
        
        .command-item {
            padding: 15px 20px;
            background: linear-gradient(135deg, #6366f1, #8b5cf6);
            color: white;
            border-radius: 12px;
            font-weight: 500;
            text-align: center;
            box-shadow: 0 8px 25px rgba(99, 102, 241, 0.3);
            transition: transform 0.2s ease;
        }
        
        .command-item:hover {
            transform: scale(1.05);
        }
        
        .stats-row {
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 15px 0;
            border-top: 1px solid #e2e8f0;
            font-size: 0.95em;
        }
        
        .stat-item {
            display: flex;
            align-items: center;
            color: #718096;
        }
        
        .stat-item i {
            margin-right: 8px;
            color: #a0aec0;
        }
        
        .stat-value {
            font-weight: 600;
            color: #2d3748;
            margin-left: 5px;
        }
        
        .footer {
            text-align: center;
            color: rgba(255, 255, 255, 0.8);
            font-size: 1em;
            font-weight: 400;
            padding: 30px 20px;
            background: rgba(255, 255, 255, 0.1);
            backdrop-filter: blur(10px);
            border-radius: 20px;
            border: 1px solid rgba(255, 255, 255, 0.1);
        }
        
        .pulse {
            animation: pulse 2s ease-in-out infinite;
        }
        
        @keyframes pulse {
            0%, 100% { opacity: 1; }
            50% { opacity: 0.7; }
        }
        
        .loading-spinner {
            display: inline-block;
            width: 20px;
            height: 20px;
            border: 2px solid #f3f4f6;
            border-radius: 50%;
            border-top-color: #6366f1;
            animation: spin 1s ease-in-out infinite;
            margin-right: 10px;
        }
        
        @keyframes spin {
            to { transform: rotate(360deg); }
        }
        
        @media (max-width: 768px) {
            .container { padding: 15px; }
            .header h1 { font-size: 2.5em; }
            .header h3 { font-size: 1.1em; }
            .dashboard { grid-template-columns: 1fr; gap: 20px; }
            .metric-card { padding: 25px; }
            .metric-value { font-size: 2.2em; }
        }
    </style>
</head>
<body>
    <!-- Animated background particles -->
    <div class="particles">
        <div class="particle" style="left: 10%; animation-delay: 0s; width: 4px; height: 4px;"></div>
        <div class="particle" style="left: 20%; animation-delay: 1s; width: 6px; height: 6px;"></div>
        <div class="particle" style="left: 30%; animation-delay: 2s; width: 3px; height: 3px;"></div>
        <div class="particle" style="left: 40%; animation-delay: 3s; width: 5px; height: 5px;"></div>
        <div class="particle" style="left: 50%; animation-delay: 4s; width: 4px; height: 4px;"></div>
        <div class="particle" style="left: 60%; animation-delay: 5s; width: 6px; height: 6px;"></div>
        <div class="particle" style="left: 70%; animation-delay: 2.5s; width: 3px; height: 3px;"></div>
        <div class="particle" style="left: 80%; animation-delay: 1.5s; width: 5px; height: 5px;"></div>
        <div class="particle" style="left: 90%; animation-delay: 3.5s; width: 4px; height: 4px;"></div>
    </div>

    <div class="container">
        <div class="header">
            <h1><i class="fas fa-seedling"></i> IOTricity</h1>
            <h3><i class="fas fa-wifi"></i> Smart Greenhouse Monitoring System</h3>
        </div>

        <div id="connection-status" class="status disconnected">
            <div class="loading-spinner"></div>
            <i class="fas fa-plug"></i> Connecting to MQTT...
        </div>

        <div class="dashboard">
            <div class="metric-card temperature">
                <div class="metric-icon"><i class="fas fa-thermometer-half"></i></div>
                <div class="metric-label">Temperature</div>
                <div class="metric-value" id="temperature">--</div>
                <div class="metric-unit">Celsius</div>
            </div>
            
            <div class="metric-card humidity">
                <div class="metric-icon"><i class="fas fa-tint"></i></div>
                <div class="metric-label">Humidity</div>
                <div class="metric-value" id="humidity">--</div>
                <div class="metric-unit">% Relative</div>
            </div>
            
            <div class="metric-card soil">
                <div class="metric-icon"><i class="fas fa-mountain"></i></div>
                <div class="metric-label">Soil Moisture</div>
                <div class="metric-value" id="soil_moisture">--</div>
                <div class="metric-unit">Theta Value</div>
            </div>
            
            <div class="metric-card light">
                <div class="metric-icon"><i class="fas fa-sun"></i></div>
                <div class="metric-label">Light Intensity</div>
                <div class="metric-value" id="light_intensity">--</div>
                <div class="metric-unit">PPFD</div>
            </div>
            
            <div class="metric-card co2">
                <div class="metric-icon"><i class="fas fa-cloud"></i></div>
                <div class="metric-label">CO₂ Level</div>
                <div class="metric-value" id="co2_level">--</div>
                <div class="metric-unit">ppm</div>
            </div>
        </div>

        <div class="commands-section">
            <div class="commands-header">
                <i class="fas fa-robot"></i>
                AI Control Commands
            </div>
            <div class="commands-grid" id="commands-list">
                <div class="command-item pulse">
                    <i class="fas fa-spinner fa-spin"></i> Waiting for commands...
                </div>
            </div>
            
            <div class="stats-row">
                <div class="stat-item">
                    <i class="fas fa-clock"></i>
                    Last Update: <span class="stat-value" id="last-update">Never</span>
                </div>
                <div class="stat-item">
                    <i class="fas fa-database"></i>
                    Data Points: <span class="stat-value" id="data-count">0</span>
                </div>
                <div class="stat-item">
                    <i class="fas fa-signal"></i>
                    Connection: <span class="stat-value" id="connection-indicator">Offline</span>
                </div>
            </div>
        </div>

        <div class="footer">
            <p>
                <i class="fas fa-rocket"></i> 
                <strong>IOTricity Dashboard</strong> 
                | Real-time IoT Greenhouse Monitoring
                <br>
                <small>Powered by Flask + Socket.IO + MQTT</small>
            </p>
        </div>
    </div>

    <script>
        const socket = io();
        
        // Initialize UI elements
        const statusDiv = document.getElementById('connection-status');
        const connectionIndicator = document.getElementById('connection-indicator');
        
        socket.on('connect', function() {
            console.log('🔗 Connected to Flask-SocketIO');
            updateConnectionStatus(true);
        });
        
        socket.on('mqtt_data', function(data) {
            console.log('📊 Received data:', data);
            updateConnectionStatus(true);
            updateMetrics(data);
            updateCommands(data);
            updateStats(data);
        });
        
        socket.on('disconnect', function() {
            console.log('🔌 Disconnected from Flask-SocketIO');
            updateConnectionStatus(false);
        });
        
        function updateConnectionStatus(connected) {
            if (connected) {
                statusDiv.className = 'status connected';
                statusDiv.innerHTML = '<i class="fas fa-check-circle"></i> MQTT Connected - Receiving Live Data';
                connectionIndicator.textContent = 'Online';
                connectionIndicator.style.color = '#10b981';
            } else {
                statusDiv.className = 'status disconnected';
                statusDiv.innerHTML = '<i class="fas fa-exclamation-triangle"></i> Disconnected from Dashboard';
                connectionIndicator.textContent = 'Offline';
                connectionIndicator.style.color = '#ef4444';
            }
        }
        
        function updateMetrics(data) {
            // Animate value changes
            animateValue('temperature', data.temperature);
            animateValue('humidity', data.humidity);
            animateValue('soil_moisture', data.soil_moisture);
            animateValue('light_intensity', data.light_intensity);
            animateValue('co2_level', data.co2_level);
        }
        
        function animateValue(elementId, newValue) {
            const element = document.getElementById(elementId);
            if (element) {
                element.style.transform = 'scale(1.1)';
                element.style.transition = 'all 0.3s ease';
                
                setTimeout(() => {
                    element.textContent = newValue;
                    element.style.transform = 'scale(1)';
                }, 150);
            }
        }
        
        function updateCommands(data) {
            const commandsList = document.getElementById('commands-list');
            
            if (data.commands && data.commands.length > 0) {
                commandsList.innerHTML = data.commands.map((cmd, index) => {
                    const icons = {
                        'fan': 'fas fa-fan',
                        'safety': 'fas fa-shield-alt',
                        'irrigation': 'fas fa-tint',
                        'heating': 'fas fa-fire',
                        'cooling': 'fas fa-snowflake',
                        'default': 'fas fa-cog'
                    };
                    
                    const icon = icons[cmd.toLowerCase()] || icons['default'];
                    
                    return `
                        <div class="command-item" style="animation-delay: ${index * 0.1}s;">
                            <i class="${icon}"></i> ${cmd.charAt(0).toUpperCase() + cmd.slice(1)}
                        </div>
                    `;
                }).join('');
            } else {
                commandsList.innerHTML = `
                    <div class="command-item pulse">
                        <i class="fas fa-hourglass-half"></i> Waiting for AI commands...
                    </div>
                `;
            }
        }
        
        function updateStats(data) {
            document.getElementById('last-update').textContent = data.last_update;
            document.getElementById('data-count').textContent = data.data_count;
        }
        
        // Auto-reload page if disconnected for too long
        let disconnectTimer = null;
        socket.on('disconnect', function() {
            disconnectTimer = setTimeout(() => {
                console.log('🔄 Auto-reloading due to extended disconnection...');
                location.reload();
            }, 15000); // Reload after 15 seconds
        });
        
        socket.on('connect', function() {
            if (disconnectTimer) {
                clearTimeout(disconnectTimer);
                disconnectTimer = null;
            }
        });
        
        // Add some interactive elements
        document.addEventListener('DOMContentLoaded', function() {
            // Add hover effects to metric cards
            const metricCards = document.querySelectorAll('.metric-card');
            metricCards.forEach(card => {
                card.addEventListener('mouseenter', function() {
                    this.style.transform = 'translateY(-10px) scale(1.02)';
                });
                
                card.addEventListener('mouseleave', function() {
                    this.style.transform = 'translateY(0) scale(1)';
                });
            });
            
            // Initialize connection status
            updateConnectionStatus(false);
        });
    </script>
</body>
</html>
'''

# MQTT Client Setup
mqtt_client = mqtt.Client()

def on_connect(client, userdata, flags, rc):
    if rc == 0:
        logger.info("✅ Connected to MQTT broker.hivemq.com")
        latest_data['connected'] = True
        client.subscribe(TELEMETRY_TOPIC)
        client.subscribe(COMMAND_TOPIC)
        socketio.emit('mqtt_data', latest_data)
    else:
        logger.error(f"❌ Failed to connect to MQTT broker. Code: {rc}")
        latest_data['connected'] = False

def on_message(client, userdata, msg):
    try:
        topic = msg.topic
        payload = msg.payload.decode('utf-8')
        
        if topic == TELEMETRY_TOPIC:
            # Parse ESP32 telemetry data
            data = json.loads(payload)
            
            # Update global state
            latest_data.update({
                'device_id': data.get('device_id', 'A1'),
                'temperature': f"{data.get('T', 'N/A'):.1f}",
                'humidity': f"{data.get('RH', 'N/A')}",
                'soil_moisture': f"{data.get('soil_theta', 'N/A')}",
                'light_intensity': f"{data.get('PPFD', 'N/A'):.1f}",
                'co2_level': f"{data.get('CO2', 'N/A'):.0f}",
                'last_update': datetime.now().strftime("%H:%M:%S"),
                'connected': True,
                'data_count': latest_data['data_count'] + 1
            })
            
            logger.info(f"📊 Data: T={latest_data['temperature']}°C, soil={latest_data['soil_moisture']}")
            
        elif topic == COMMAND_TOPIC:
            # Parse AI commands
            try:
                commands = json.loads(payload)
                if isinstance(commands, list):
                    latest_data['commands'] = commands[:5]  # Keep last 5 commands
                    logger.info(f"🤖 Command: {commands}")
            except:
                latest_data['commands'].append(payload)
        
        # Emit to all connected clients
        socketio.emit('mqtt_data', latest_data)
        
    except json.JSONDecodeError:
        logger.error(f"❌ Invalid JSON in {topic}: {payload}")
    except Exception as e:
        logger.error(f"❌ Error processing message: {e}")

def on_disconnect(client, userdata, rc):
    logger.warning("🔌 Disconnected from MQTT broker")
    latest_data['connected'] = False
    socketio.emit('mqtt_data', latest_data)

# Configure MQTT callbacks
mqtt_client.on_connect = on_connect
mqtt_client.on_message = on_message
mqtt_client.on_disconnect = on_disconnect

@app.route('/')
def dashboard():
    """Serve the dashboard HTML"""
    return render_template_string(HTML_TEMPLATE)

@app.route('/api/status')
def api_status():
    """API endpoint for current status"""
    return jsonify(latest_data)

@socketio.on('connect')
def handle_connect():
    """Handle WebSocket connections"""
    logger.info("🔗 Client connected to SocketIO")
    emit('mqtt_data', latest_data)

@socketio.on('disconnect')
def handle_disconnect():
    """Handle WebSocket disconnections"""
    logger.info("🔌 Client disconnected from SocketIO")

def start_mqtt():
    """Start MQTT connection in background thread"""
    try:
        logger.info("🚀 Connecting to MQTT broker...")
        mqtt_client.connect(MQTT_BROKER, MQTT_PORT, 60)
        mqtt_client.loop_start()
    except Exception as e:
        logger.error(f"❌ MQTT connection failed: {e}")

if __name__ == '__main__':
    print("🚀 Starting IOTricity Flask Dashboard...")
    print(f"🌐 Dashboard will be available at: http://localhost:{FLASK_PORT}")
    print("📡 Connecting to MQTT for live ESP32 data...")
    print()
    print("👆 Open the URL above in your browser to see live data! 👆")
    
    # Start MQTT in background
    mqtt_thread = threading.Thread(target=start_mqtt)
    mqtt_thread.daemon = True
    mqtt_thread.start()
    
    # Start Flask-SocketIO server
    socketio.run(app, host='0.0.0.0', port=FLASK_PORT, debug=False)
