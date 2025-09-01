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
    'ai_commands': [],
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
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
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
            margin: 0;
            padding: 20px;
        }
        
        .main-container {
            max-width: 1600px;
            margin: 0 auto;
            padding: 0 20px;
        }
        
        .grid-layout {
            display: grid;
            grid-template-columns: 1fr 400px;
            gap: 30px;
            margin-bottom: 30px;
        }
        
        .left-panel {
            display: flex;
            flex-direction: column;
            gap: 30px;
        }
        
        .right-panel {
            display: flex;
            flex-direction: column;
            gap: 30px;
        }
        
        .sensor-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
            gap: 25px;
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
        
        .container {
            max-width: 1400px;
            margin: 0 auto;
            padding: 20px;
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
        
        .sensor-card {
            background: rgba(255, 255, 255, 0.95);
            backdrop-filter: blur(15px);
            border-radius: 20px;
            padding: 25px;
            box-shadow: 0 20px 40px rgba(0,0,0,0.1);
            border: 1px solid rgba(255, 255, 255, 0.2);
            transition: transform 0.3s ease, box-shadow 0.3s ease;
            position: relative;
            overflow: hidden;
        }
        
        .sensor-card:hover {
            transform: translateY(-5px);
            box-shadow: 0 30px 60px rgba(0,0,0,0.2);
        }
        
        .sensor-card::before {
            content: '';
            position: absolute;
            top: 0;
            left: 0;
            right: 0;
            height: 4px;
            background: var(--accent-color);
            border-radius: 20px 20px 0 0;
        }
        
        .sensor-header {
            display: flex;
            align-items: center;
            justify-content: space-between;
            margin-bottom: 20px;
        }
        
        .sensor-title {
            display: flex;
            align-items: center;
            font-size: 1.1em;
            font-weight: 600;
            color: #2d3748;
        }
        
        .sensor-icon {
            font-size: 1.5em;
            margin-right: 12px;
            color: var(--accent-color);
        }
        
        .sensor-value {
            font-size: 1.8em;
            font-weight: 700;
            color: var(--accent-color);
        }
        
        .sensor-unit {
            font-size: 0.9em;
            color: #718096;
            margin-left: 5px;
        }
        
        .sensor-chart {
            height: 120px;
            margin-top: 15px;
        }
        
        .status-indicator {
            width: 12px;
            height: 12px;
            border-radius: 50%;
            background: var(--accent-color);
            animation: pulse 2s infinite;
        }
        
        .temperature { --accent-color: #ef4444; }
        .humidity { --accent-color: #3b82f6; }
        .soil { --accent-color: #8b5cf6; }
        .light { --accent-color: #f59e0b; }
        .co2 { --accent-color: #10b981; }
        
        .control-panel {
            background: rgba(255, 255, 255, 0.95);
            backdrop-filter: blur(15px);
            border-radius: 20px;
            padding: 25px;
            box-shadow: 0 20px 40px rgba(0,0,0,0.1);
            border: 1px solid rgba(255, 255, 255, 0.2);
        }
        
        .panel-header {
            display: flex;
            align-items: center;
            margin-bottom: 20px;
            font-size: 1.3em;
            font-weight: 600;
            color: #2d3748;
        }
        
        .panel-icon {
            font-size: 1.5em;
            margin-right: 12px;
            color: #6366f1;
        }
        
        .ai-commands-grid {
            display: grid;
            gap: 12px;
        }
        
        .command-chip {
            display: flex;
            align-items: center;
            padding: 12px 16px;
            background: linear-gradient(135deg, #6366f1, #8b5cf6);
            color: white;
            border-radius: 25px;
            font-weight: 500;
            font-size: 0.95em;
            box-shadow: 0 4px 15px rgba(99, 102, 241, 0.3);
            transition: all 0.3s ease;
        }
        
        .command-chip:hover {
            transform: translateY(-2px);
            box-shadow: 0 8px 25px rgba(99, 102, 241, 0.4);
        }
        
        .command-chip i {
            margin-right: 10px;
            font-size: 1.1em;
        }
        
        .system-stats {
            display: grid;
            gap: 15px;
        }
        
        .stat-row {
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 12px 0;
            border-bottom: 1px solid #e2e8f0;
        }
        
        .stat-row:last-child {
            border-bottom: none;
        }
        
        .stat-label {
            display: flex;
            align-items: center;
            color: #718096;
            font-size: 0.95em;
        }
        
        .stat-label i {
            margin-right: 8px;
            width: 16px;
        }
        
        .stat-value {
            font-weight: 600;
            color: #2d3748;
        }
        
        .connection-badge {
            display: inline-flex;
            align-items: center;
            padding: 6px 12px;
            border-radius: 20px;
            font-size: 0.85em;
            font-weight: 500;
        }
        
        .badge-online {
            background: #d1fae5;
            color: #065f46;
        }
        
        .badge-offline {
            background: #fee2e2;
            color: #991b1b;
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
        
        @media (max-width: 1200px) {
            .grid-layout {
                grid-template-columns: 1fr;
                gap: 25px;
            }
            
            .right-panel {
                flex-direction: row;
                gap: 25px;
            }
        }
        
        @media (max-width: 768px) {
            .main-container {
                padding: 0 15px;
            }
            
            body {
                padding: 15px;
            }
            
            .header h1 {
                font-size: 2.5em;
            }
            
            .header h3 {
                font-size: 1.1em;
            }
            
            .sensor-grid {
                grid-template-columns: 1fr;
                gap: 20px;
            }
            
            .right-panel {
                flex-direction: column;
            }
            
            .sensor-card {
                padding: 20px;
            }
            
            .sensor-value {
                font-size: 1.5em;
            }
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

    <div class="main-container">
        <!-- Header -->
        <div class="header">
            <h1><i class="fas fa-seedling"></i> IOTricity</h1>
            <h3><i class="fas fa-wifi"></i> Smart Greenhouse Monitoring System</h3>
        </div>

        <!-- Connection Status -->
        <div id="connection-status" class="status disconnected">
            <div class="loading-spinner"></div>
            <i class="fas fa-plug"></i> Connecting to MQTT...
        </div>

        <!-- Main Dashboard Layout -->
        <div class="grid-layout">
            <!-- Left Panel - Sensor Data -->
            <div class="left-panel">
                <div class="sensor-grid">
                    <!-- Temperature Sensor -->
                    <div class="sensor-card temperature">
                        <div class="sensor-header">
                            <div class="sensor-title">
                                <div class="sensor-icon"><i class="fas fa-thermometer-half"></i></div>
                                Temperature
                            </div>
                            <div class="sensor-value">
                                <span id="temperature">--</span>
                                <span class="sensor-unit">°C</span>
                            </div>
                        </div>
                        <div class="sensor-chart">
                            <canvas id="temp-chart"></canvas>
                        </div>
                        <div class="status-indicator"></div>
                    </div>

                    <!-- Humidity Sensor -->
                    <div class="sensor-card humidity">
                        <div class="sensor-header">
                            <div class="sensor-title">
                                <div class="sensor-icon"><i class="fas fa-tint"></i></div>
                                Humidity
                            </div>
                            <div class="sensor-value">
                                <span id="humidity">--</span>
                                <span class="sensor-unit">%</span>
                            </div>
                        </div>
                        <div class="sensor-chart">
                            <canvas id="humidity-chart"></canvas>
                        </div>
                        <div class="status-indicator"></div>
                    </div>

                    <!-- Soil Moisture Sensor -->
                    <div class="sensor-card soil">
                        <div class="sensor-header">
                            <div class="sensor-title">
                                <div class="sensor-icon"><i class="fas fa-mountain"></i></div>
                                Soil Moisture
                            </div>
                            <div class="sensor-value">
                                <span id="soil_moisture">--</span>
                                <span class="sensor-unit">θ</span>
                            </div>
                        </div>
                        <div class="sensor-chart">
                            <canvas id="soil-chart"></canvas>
                        </div>
                        <div class="status-indicator"></div>
                    </div>

                    <!-- Light Intensity Sensor -->
                    <div class="sensor-card light">
                        <div class="sensor-header">
                            <div class="sensor-title">
                                <div class="sensor-icon"><i class="fas fa-sun"></i></div>
                                Light Intensity
                            </div>
                            <div class="sensor-value">
                                <span id="light_intensity">--</span>
                                <span class="sensor-unit">PPFD</span>
                            </div>
                        </div>
                        <div class="sensor-chart">
                            <canvas id="light-chart"></canvas>
                        </div>
                        <div class="status-indicator"></div>
                    </div>

                    <!-- CO2 Sensor -->
                    <div class="sensor-card co2">
                        <div class="sensor-header">
                            <div class="sensor-title">
                                <div class="sensor-icon"><i class="fas fa-cloud"></i></div>
                                CO₂ Level
                            </div>
                            <div class="sensor-value">
                                <span id="co2_level">--</span>
                                <span class="sensor-unit">ppm</span>
                            </div>
                        </div>
                        <div class="sensor-chart">
                            <canvas id="co2-chart"></canvas>
                        </div>
                        <div class="status-indicator"></div>
                    </div>
                </div>
            </div>

            <!-- Right Panel - Controls & Stats -->
            <div class="right-panel">
                <!-- AI Commands Panel -->
                <div class="control-panel">
                    <div class="panel-header">
                        <div class="panel-icon"><i class="fas fa-robot"></i></div>
                        AI Control Commands
                    </div>
                    <div class="ai-commands-grid" id="commands-list">
                        <div class="command-chip pulse">
                            <i class="fas fa-spinner fa-spin"></i> Waiting for AI...
                        </div>
                    </div>
                </div>

                <!-- System Stats Panel -->
                <div class="control-panel">
                    <div class="panel-header">
                        <div class="panel-icon"><i class="fas fa-chart-line"></i></div>
                        System Status
                    </div>
                    <div class="system-stats">
                        <div class="stat-row">
                            <div class="stat-label">
                                <i class="fas fa-clock"></i>
                                Last Update
                            </div>
                            <div class="stat-value" id="last-update">Never</div>
                        </div>
                        <div class="stat-row">
                            <div class="stat-label">
                                <i class="fas fa-database"></i>
                                Data Points
                            </div>
                            <div class="stat-value" id="data-count">0</div>
                        </div>
                        <div class="stat-row">
                            <div class="stat-label">
                                <i class="fas fa-signal"></i>
                                MQTT Status
                            </div>
                            <div class="connection-badge badge-offline" id="connection-badge">
                                Offline
                            </div>
                        </div>
                        <div class="stat-row">
                            <div class="stat-label">
                                <i class="fas fa-microchip"></i>
                                Device ID
                            </div>
                            <div class="stat-value">A1</div>
                        </div>
                    </div>
                </div>
            </div>
        </div>

        <!-- Footer -->
        <div class="footer">
            <p>
                <i class="fas fa-rocket"></i> 
                <strong>IOTricity Dashboard v2.0</strong> 
                | Real-time IoT Greenhouse Monitoring with Live Charts
                <br>
                <small>Powered by Flask + Socket.IO + Plotly.js</small>
            </p>
        </div>
    </div>

    <script>
        const socket = io();
        
        // Chart instances storage
        const charts = {};
        const MAX_POINTS = 15;
        
        // Chart colors matching sensor types
        const chartColors = {
            temperature: '#ef4444',
            humidity: '#3b82f6',
            soil_moisture: '#8b5cf6',
            light_intensity: '#f59e0b',
            co2_level: '#10b981'
        };
        
        // Initialize all charts
        function initializeCharts() {
            const sensors = [
                { key: 'temperature', canvas: 'temp-chart', label: 'Temperature (°C)' },
                { key: 'humidity', canvas: 'humidity-chart', label: 'Humidity (%)' },
                { key: 'soil_moisture', canvas: 'soil-chart', label: 'Soil Moisture' },
                { key: 'light_intensity', canvas: 'light-chart', label: 'Light (PPFD)' },
                { key: 'co2_level', canvas: 'co2-chart', label: 'CO₂ (ppm)' }
            ];
            
            sensors.forEach(sensor => {
                const ctx = document.getElementById(sensor.canvas);
                if (ctx) {
                    charts[sensor.key] = new Chart(ctx, {
                        type: 'line',
                        data: {
                            labels: [],
                            datasets: [{
                                label: sensor.label,
                                data: [],
                                borderColor: chartColors[sensor.key],
                                backgroundColor: chartColors[sensor.key] + '20',
                                borderWidth: 3,
                                pointRadius: 4,
                                pointBackgroundColor: chartColors[sensor.key],
                                pointBorderColor: '#ffffff',
                                pointBorderWidth: 2,
                                fill: true,
                                tension: 0.4
                            }]
                        },
                        options: {
                            responsive: true,
                            maintainAspectRatio: false,
                            plugins: {
                                legend: {
                                    display: false
                                }
                            },
                            scales: {
                                x: {
                                    display: false
                                },
                                y: {
                                    display: false,
                                    beginAtZero: true
                                }
                            },
                            elements: {
                                point: {
                                    hoverRadius: 8
                                }
                            },
                            animation: {
                                duration: 750,
                                easing: 'easeOutCubic'
                            }
                        }
                    });
                }
            });
            
            console.log('📊 Charts initialized:', Object.keys(charts));
        }
        
        // Update specific chart with new data
        function updateChart(sensorKey, value, timestamp) {
            const chart = charts[sensorKey];
            if (!chart) return;
            
            const numValue = parseFloat(value) || 0;
            
            // Add new data point
            chart.data.labels.push(timestamp);
            chart.data.datasets[0].data.push(numValue);
            
            // Keep only last MAX_POINTS
            if (chart.data.labels.length > MAX_POINTS) {
                chart.data.labels.shift();
                chart.data.datasets[0].data.shift();
            }
            
            // Update the chart
            chart.update('none'); // No animation for smoother updates
        }
        
        // Socket event handlers
        socket.on('connect', function() {
            console.log('🔗 Connected to Flask-SocketIO');
            updateConnectionStatus(true);
        });
        
        socket.on('mqtt_data', function(data) {
            console.log('📊 Received data:', data);
            updateConnectionStatus(true);
            updateSensorValues(data);
            updateCommands(data);
            updateSystemStats(data);
            
            // Update all charts with new data
            const timestamp = new Date().toLocaleTimeString();
            updateChart('temperature', data.temperature, timestamp);
            updateChart('humidity', data.humidity, timestamp);
            updateChart('soil_moisture', data.soil_moisture, timestamp);
            updateChart('light_intensity', data.light_intensity, timestamp);
            updateChart('co2_level', data.co2_level, timestamp);
        });
        
        socket.on('disconnect', function() {
            console.log('🔌 Disconnected from Flask-SocketIO');
            updateConnectionStatus(false);
        });
        
        function updateConnectionStatus(connected) {
            const statusDiv = document.getElementById('connection-status');
            const connectionBadge = document.getElementById('connection-badge');
            
            if (connected) {
                statusDiv.className = 'status connected';
                statusDiv.innerHTML = '<i class="fas fa-check-circle"></i> MQTT Connected - Live Data + Charts';
                connectionBadge.textContent = 'Online';
                connectionBadge.className = 'connection-badge badge-online';
            } else {
                statusDiv.className = 'status disconnected';
                statusDiv.innerHTML = '<i class="fas fa-exclamation-triangle"></i> Disconnected from Dashboard';
                connectionBadge.textContent = 'Offline';
                connectionBadge.className = 'connection-badge badge-offline';
            }
        }
        
        function updateSensorValues(data) {
            // Clean numeric values for display
            const values = {
                temperature: parseFloat(data.temperature).toFixed(1),
                humidity: parseFloat(data.humidity).toFixed(0),
                soil_moisture: parseFloat(data.soil_moisture).toFixed(3),
                light_intensity: parseFloat(data.light_intensity).toFixed(1),
                co2_level: Math.round(parseFloat(data.co2_level))
            };
            
            // Animate value changes
            animateValue('temperature', values.temperature);
            animateValue('humidity', values.humidity);
            animateValue('soil_moisture', values.soil_moisture);
            animateValue('light_intensity', values.light_intensity);
            animateValue('co2_level', values.co2_level);
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
                        <div class="command-chip" style="animation-delay: ${index * 0.1}s;">
                            <i class="${icon}"></i> 
                            ${cmd.charAt(0).toUpperCase() + cmd.slice(1)}
                        </div>
                    `;
                }).join('');
            } else {
                commandsList.innerHTML = `
                    <div class="command-chip pulse">
                        <i class="fas fa-hourglass-half"></i> 
                        Waiting for AI commands...
                    </div>
                `;
            }
        }
        
        function updateSystemStats(data) {
            document.getElementById('last-update').textContent = data.last_update || 'Never';
            document.getElementById('data-count').textContent = data.data_count || '0';
        }
        
        // Auto-reload on extended disconnection
        let disconnectTimer = null;
        socket.on('disconnect', function() {
            disconnectTimer = setTimeout(() => {
                console.log('🔄 Auto-reloading due to disconnection...');
                location.reload();
            }, 15000);
        });
        
        socket.on('connect', function() {
            if (disconnectTimer) {
                clearTimeout(disconnectTimer);
                disconnectTimer = null;
            }
        });
        
        // Initialize everything when page loads
        document.addEventListener('DOMContentLoaded', function() {
            console.log('🚀 Initializing IOTricity Dashboard v2.0 with Charts...');
            
            // Wait a moment for the DOM to be fully ready, then initialize charts
            setTimeout(() => {
                initializeCharts();
                updateConnectionStatus(false);
                
                // Add hover effects to sensor cards
                const sensorCards = document.querySelectorAll('.sensor-card');
                sensorCards.forEach(card => {
                    card.addEventListener('mouseenter', function() {
                        this.style.transform = 'translateY(-5px) scale(1.02)';
                    });
                    
                    card.addEventListener('mouseleave', function() {
                        this.style.transform = 'translateY(0) scale(1)';
                    });
                });
                
                console.log('✅ Dashboard v2.0 initialized with live charts!');
            }, 100);
        });
    </script>
</body>
</html>
'''

# MQTT Client Setup
try:
    # Try newer version first
    import paho.mqtt.client as mqtt_temp
    if hasattr(mqtt_temp, 'CallbackAPIVersion'):
        mqtt_client = mqtt.Client(callback_api_version=mqtt_temp.CallbackAPIVersion.VERSION2)
    else:
        mqtt_client = mqtt.Client()
except:
    mqtt_client = mqtt.Client()

def on_connect(client, userdata, flags, rc, properties=None):
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
                cmd_data = json.loads(payload)
                if 'actions' in cmd_data and isinstance(cmd_data['actions'], dict):
                    # Extract action names and details for display
                    actions = []
                    for action_name, action_details in cmd_data['actions'].items():
                        if action_name == 'irrigation' and action_details.get('action') == 'on':
                            duration = action_details.get('duration_s', 'N/A')
                            actions.append(f"Irrigation ({duration}s)")
                        elif action_name == 'fan' and 'duty' in action_details:
                            duty = int(action_details['duty'] * 100)
                            actions.append(f"Fan ({duty}%)")
                        elif action_name == 'safety' and action_details.get('action') == 'safe_mode':
                            actions.append("Safety Mode")
                        else:
                            actions.append(action_name.title())
                    
                    latest_data['commands'] = actions
                    latest_data['ai_commands'].append({
                        'timestamp': datetime.now().strftime("%H:%M:%S"),
                        'cmd_id': cmd_data.get('cmd_id', 'N/A'),
                        'actions': actions
                    })
                    
                    # Keep only last 10 AI command logs
                    if len(latest_data['ai_commands']) > 10:
                        latest_data['ai_commands'] = latest_data['ai_commands'][-10:]
                    
                    logger.info(f"🤖 AI Command: {actions}")
            except Exception as cmd_error:
                logger.error(f"❌ Error parsing command: {cmd_error}")
        
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
