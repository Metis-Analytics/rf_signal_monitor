# RF Signal Monitoring System

This project implements a Remote RF Signal Monitoring System using HackRF One SDR with GPS location tracking.

## Setup

1. Install the required dependencies:
```bash
pip install -r requirements.txt
```

2. Connect your HackRF One device.

3. Connect your GPS module (default port is COM5, can be configured via environment variables).

4. Run the application:
```bash
python app.py
```

5. Open a web browser and navigate to `http://localhost:8000`

## Features

- Real-time RF signal monitoring
- Spectrum analysis and visualization
- Device detection and tracking
- GPS location integration
- Whitelist management for known devices
- WebSocket-based real-time updates
- RESTful API for data access and management

## Hardware Requirements

- HackRF One SDR
- GPS module (NMEA compatible)
- Python 3.7+
- Raspberry Pi 4 (recommended for deployment)

## Project Structure

- `app.py`: Main FastAPI application
- `rf_monitor.py`: RF monitoring implementation
- `gps_module.py`: GPS module integration
- `static/`: Frontend assets (HTML, CSS, JavaScript)
- `requirements.txt`: Python package dependencies
- `api_documentation.md`: Detailed API documentation
- `project.md`: Project documentation and planning

## API Documentation

The system provides a RESTful API for accessing monitoring data and managing the whitelist. See `api_documentation.md` for detailed information on available endpoints.

Key endpoints:
- `/api/devices`: Get all detected RF devices
- `/api/whitelist`: Manage whitelisted devices
- `/api/monitoring_station`: Get current GPS location and status
- `/ws`: WebSocket endpoint for real-time updates

## Configuration

You can modify the following parameters:
- GPS port: Set the `GPS_PORT` environment variable (default: COM5)
- Sample rate: Default 2.048MHz
- Center frequency: Default 915MHz

## Data Storage

The application stores:
- `whitelist.json`: List of known and approved devices
- `devices_db.json`: Database of all detected devices

## License

MIT
