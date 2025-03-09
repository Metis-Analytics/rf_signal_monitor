# RF Signal Monitoring API Documentation

This document provides details about the API endpoints available in the RF Signal Monitoring application.

## Table of Contents
- [Web Interface](#web-interface)
- [Device Management](#device-management)
- [Whitelist Management](#whitelist-management)
- [Monitoring Station](#monitoring-station)
- [WebSocket Connection](#websocket-connection)

## Web Interface

### Get Main Web Interface
Serves the main HTML page for the web interface.

- **URL**: `/`
- **Method**: `GET`
- **Response**: HTML content of the main application interface

## Device Management

### Get All Devices
Retrieves all detected RF devices, including both active and inactive devices.

- **URL**: `/api/devices`
- **Method**: `GET`
- **Response**: JSON object containing:
  - `devices`: Array of device objects with the following properties:
    - `id`: Unique device identifier (string)
    - `name`: Device name (string, if available)
    - `type`: Device type (e.g., "GSM", "LTE", "UMTS", "WiFi", "Bluetooth")
    - `frequency`: Operating frequency in MHz (number)
    - `power`: Signal power in dB (number)
    - `first_seen`: ISO timestamp of when the device was first detected (string)
    - `last_seen`: ISO timestamp of when the device was last detected (string)
    - `whitelisted`: Boolean indicating if the device is in the whitelist
    - `simulated_id`: Simulated IMSI/IMEI identifier (string)
    - `location`: Object containing:
      - `latitude`: Latitude coordinate (number)
      - `longitude`: Longitude coordinate (number)
    - `isActive`: Boolean indicating if the device is currently active
  - `spectrum`: Array of spectrum data points (if available)
  - `monitoring_station`: Object containing:
    - `latitude`: Latitude coordinate of the monitoring station (number)
    - `longitude`: Longitude coordinate of the monitoring station (number)
    - `altitude`: Altitude in meters (number)
    - `num_satellites`: Number of GPS satellites used for location fix (string)
    - `hdop`: Horizontal dilution of precision (number)

- **Example Response**:
```json
{
  "devices": [
    {
      "id": "5213ec08",
      "name": "Unknown Device",
      "type": "GSM",
      "frequency": 915.23,
      "power": -45.7,
      "first_seen": "2025-03-08T10:15:23.456Z",
      "last_seen": "2025-03-08T10:30:45.789Z",
      "whitelisted": false,
      "simulated_id": "310451234567890",
      "location": {
        "latitude": 38.573955,
        "longitude": -90.284148
      },
      "isActive": true
    }
  ],
  "spectrum": [],
  "monitoring_station": {
    "latitude": 38.573955,
    "longitude": -90.284148,
    "altitude": 144.6,
    "num_satellites": "06",
    "hdop": 1.67
  }
}
```

## Whitelist Management

### Add Device to Whitelist
Adds a device to the whitelist.

- **URL**: `/api/whitelist/{device_id}`
- **Method**: `POST`
- **URL Parameters**:
  - `device_id`: ID of the device to add to the whitelist
- **Request Body**: JSON object containing:
  - `name`: Device name (string)
  - `type`: Device type (string)
  - `frequency`: Operating frequency in MHz (number)
  - `first_seen`: ISO timestamp of when the device was first detected (string, optional)
  - `last_seen`: ISO timestamp of when the device was last detected (string, optional)
- **Response**: JSON object containing:
  - `status`: "success" if the operation was successful
  - `message`: Description of the operation result

- **Example Request**:
```json
{
  "name": "My Phone",
  "type": "LTE",
  "frequency": 915.23,
  "first_seen": "2025-03-08T10:15:23.456Z",
  "last_seen": "2025-03-08T10:30:45.789Z"
}
```

- **Example Response**:
```json
{
  "status": "success",
  "message": "Device 5213ec08 added to whitelist"
}
```

### Remove Device from Whitelist
Removes a device from the whitelist.

- **URL**: `/api/whitelist/{device_id}`
- **Method**: `DELETE`
- **URL Parameters**:
  - `device_id`: ID of the device to remove from the whitelist
- **Response**: JSON object containing:
  - `status`: "success" if the operation was successful
  - `message`: Description of the operation result

- **Example Response**:
```json
{
  "status": "success",
  "message": "Device 5213ec08 removed from whitelist"
}
```

### Get Whitelist
Retrieves all devices in the whitelist.

- **URL**: `/api/whitelist`
- **Method**: `GET`
- **Response**: JSON object containing:
  - `whitelist`: Object with device IDs as keys and device details as values

- **Example Response**:
```json
{
  "whitelist": {
    "5213ec08": {
      "name": "My Phone",
      "type": "LTE",
      "frequency": 915.23,
      "first_seen": "2025-03-08T10:15:23.456Z",
      "last_seen": "2025-03-08T10:30:45.789Z",
      "whitelisted": true
    }
  }
}
```

## Monitoring Station

### Get Monitoring Station Information
Retrieves the current location and status of the monitoring station.

- **URL**: `/api/monitoring_station`
- **Method**: `GET`
- **Response**: JSON object containing:
  - `location`: Object containing:
    - `latitude`: Latitude coordinate (number)
    - `longitude`: Longitude coordinate (number)
    - `altitude`: Altitude in meters (number)
    - `num_satellites`: Number of GPS satellites used for location fix (string)
    - `hdop`: Horizontal dilution of precision (number)
    - `simulated`: Boolean indicating if the GPS data is simulated
  - `using_real_gps`: Boolean indicating if the system is using real GPS hardware
  - `is_connected`: Boolean indicating if the GPS module is connected and providing data

- **Example Response**:
```json
{
  "location": {
    "latitude": 38.573955,
    "longitude": -90.284148,
    "altitude": 144.6,
    "num_satellites": "06",
    "hdop": 1.67,
    "simulated": false
  },
  "using_real_gps": true,
  "is_connected": true
}
```

## WebSocket Connection

### WebSocket Endpoint
Establishes a WebSocket connection for real-time updates.

- **URL**: `/ws`
- **Protocol**: WebSocket
- **Data Sent**: The server broadcasts the same data structure as the `/api/devices` endpoint at regular intervals.

- **Example Message**:
```json
{
  "devices": [
    {
      "id": "5213ec08",
      "name": "Unknown Device",
      "type": "GSM",
      "frequency": 915.23,
      "power": -45.7,
      "first_seen": "2025-03-08T10:15:23.456Z",
      "last_seen": "2025-03-08T10:30:45.789Z",
      "whitelisted": false,
      "simulated_id": "310451234567890",
      "location": {
        "latitude": 38.573955,
        "longitude": -90.284148
      },
      "isActive": true
    }
  ],
  "spectrum": [],
  "monitoring_station": {
    "latitude": 38.573955,
    "longitude": -90.284148,
    "altitude": 144.6,
    "num_satellites": "06",
    "hdop": 1.67
  }
}
```

## Error Handling

All API endpoints return appropriate HTTP status codes:
- `200 OK`: Request was successful
- `404 Not Found`: Requested resource was not found
- `500 Internal Server Error`: Server encountered an error

Error responses include a JSON object with a `detail` field describing the error.

- **Example Error Response**:
```json
{
  "detail": "Device 5213ec08 not found in whitelist"
}
