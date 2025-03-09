#!/usr/bin/env python3
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse, HTMLResponse
from pydantic import BaseModel
from typing import Dict, List, Optional
import uvicorn
import asyncio
import json
import os
import logging
import shutil
from datetime import datetime, timedelta
import random
import uuid
import time
import traceback
from rf_monitor import RFMonitor
import asyncio
import json
import random
import math
import logging
import time
import os
import shutil
from datetime import datetime
from typing import Dict, List, Optional
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from rf_monitor import RFMonitor
import os
from gps_module import GPSModule

# Initialize logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("rf_monitor_app")

# Initialize the RF monitor
rf_monitor = RFMonitor()

# Initialize GPS module - update the port to match your GPS device
# Common ports: 'COM3' on Windows, '/dev/ttyUSB0' or '/dev/ttyACM0' on Linux
GPS_PORT = os.environ.get('GPS_PORT', 'COM5')  # Default to COM5, override with environment variable

# Default monitoring location (used when GPS is not available)
DEFAULT_MONITORING_LOCATION = {
    'latitude': 39.8283,  # Approximate center of US
    'longitude': -98.5795  # Approximate center of US
}

# Try to initialize the GPS module with the real device first
gps_module = GPSModule(port=GPS_PORT, simulation_mode=False, force_real=False)
gps_connected = False

# Try to start the GPS module
try:
    gps_module.start()
    logger.info(f"GPS module started on port {GPS_PORT}")
    
    # Check if GPS is actually connected
    time.sleep(3)  # Give it a moment to connect (increased to 3 seconds)
    if gps_module.is_connected():
        gps_connected = True
        if gps_module.is_using_real_gps():
            logger.info("Real GPS device successfully connected and providing data")
        else:
            logger.info("Using GPS simulation mode")
    else:
        logger.warning("GPS device not providing data yet, will continue trying in background")
except Exception as e:
    logger.error(f"Failed to start GPS module: {e}")
    logger.info("Switching to GPS simulation mode")
    gps_module = GPSModule(port=GPS_PORT, simulation_mode=True)
    gps_module.start()

# Create FastAPI app
app = FastAPI()

# Serve static files
app.mount("/static", StaticFiles(directory="static"), name="static")

# Device model for API
class Device(BaseModel):
    name: str
    type: Optional[str] = None
    frequency: float
    power: float
    first_seen: Optional[str] = None
    last_seen: Optional[str] = None
    location: Optional[Dict] = None
    simulated_id: Optional[str] = None

# Store for whitelisted devices
whitelist = {}

# File to store whitelist
WHITELIST_FILE = "whitelist.json"

# File to store all detected devices
DEVICES_DB_FILE = "devices_db.json"

# How long to keep a device in memory without detection (in seconds)
DEVICE_EXPIRY_TIME = 300  # 5 minutes

# Global variables
devices_db = {}
last_cleanup_time = datetime.now()

def load_whitelist():
    global whitelist
    try:
        if os.path.exists(WHITELIST_FILE):
            with open(WHITELIST_FILE, "r") as f:
                loaded_data = json.load(f)
                if isinstance(loaded_data, dict):
                    whitelist = loaded_data
                    logger.info(f"Loaded whitelist from {WHITELIST_FILE} with {len(whitelist)} devices")
                else:
                    logger.error(f"Invalid whitelist format in {WHITELIST_FILE}, starting with empty whitelist")
                    whitelist = {}
        else:
            logger.info(f"Whitelist file {WHITELIST_FILE} not found, starting with empty whitelist")
            whitelist = {}
    except Exception as e:
        logger.error(f"Error loading whitelist: {e}")
        whitelist = {}
    
    # Make a backup of the whitelist file if it exists
    if os.path.exists(WHITELIST_FILE):
        try:
            backup_file = f"{WHITELIST_FILE}.bak"
            shutil.copy2(WHITELIST_FILE, backup_file)
            logger.info(f"Created backup of whitelist at {backup_file}")
        except Exception as e:
            logger.error(f"Failed to create whitelist backup: {e}")

def verify_whitelist():
    """Verify whitelist integrity and fix any issues"""
    global whitelist
    
    try:
        # Check if whitelist is empty but file exists
        if not whitelist and os.path.exists(WHITELIST_FILE):
            logger.warning("Whitelist is empty but file exists, attempting to reload")
            load_whitelist()
        
        # Check for backup if whitelist is still empty
        if not whitelist and os.path.exists(f"{WHITELIST_FILE}.bak"):
            logger.warning("Attempting to restore whitelist from backup")
            try:
                with open(f"{WHITELIST_FILE}.bak", "r") as f:
                    backup_data = json.load(f)
                    if isinstance(backup_data, dict) and backup_data:
                        whitelist = backup_data
                        logger.info(f"Restored whitelist from backup with {len(whitelist)} devices")
                        # Save the restored whitelist
                        save_whitelist()
            except Exception as e:
                logger.error(f"Failed to restore whitelist from backup: {e}")
        
        # Log whitelist status
        logger.info(f"Whitelist verification complete: {len(whitelist)} devices in whitelist")
    except Exception as e:
        logger.error(f"Error verifying whitelist: {e}")

def save_whitelist():
    try:
        # First write to a temporary file
        temp_file = f"{WHITELIST_FILE}.tmp"
        with open(temp_file, "w") as f:
            json.dump(whitelist, f, indent=2)
        
        # Then rename the temporary file to the actual file
        # This helps prevent data corruption if the program crashes during writing
        if os.path.exists(temp_file):
            if os.path.exists(WHITELIST_FILE):
                os.replace(temp_file, WHITELIST_FILE)
            else:
                os.rename(temp_file, WHITELIST_FILE)
            
            logger.info(f"Saved whitelist to {WHITELIST_FILE} with {len(whitelist)} devices")
        else:
            logger.error(f"Failed to save whitelist: temporary file not created")
    except Exception as e:
        logger.error(f"Error saving whitelist: {e}")
        # Try a direct save as a fallback
        try:
            with open(WHITELIST_FILE, "w") as f:
                json.dump(whitelist, f)
            logger.info(f"Saved whitelist directly to {WHITELIST_FILE} with {len(whitelist)} devices")
        except Exception as e2:
            logger.error(f"Error in fallback whitelist save: {e2}")

def load_devices_db():
    global devices_db
    try:
        if os.path.exists(DEVICES_DB_FILE):
            with open(DEVICES_DB_FILE, "r") as f:
                devices_db = json.load(f)
                logger.info(f"Loaded devices database from {DEVICES_DB_FILE} with {len(devices_db)} devices")
        else:
            devices_db = {}
            logger.info("No devices database file found, starting with empty database")
    except Exception as e:
        logger.error(f"Error loading devices database: {e}")
        devices_db = {}

def save_devices_db():
    try:
        with open(DEVICES_DB_FILE, "w") as f:
            json.dump(devices_db, f)
            logger.info(f"Saved devices database to {DEVICES_DB_FILE} with {len(devices_db)} devices")
    except Exception as e:
        logger.error(f"Error saving devices database: {e}")

def cleanup_expired_devices():
    global devices_db, last_cleanup_time
    
    # Only run cleanup every minute to avoid excessive processing
    if (datetime.now() - last_cleanup_time).total_seconds() < 60:
        return
    
    current_time = datetime.now()
    expired_devices = []
    
    for device_id, device in devices_db.items():
        last_seen = datetime.fromisoformat(device['last_seen'])
        if (current_time - last_seen).total_seconds() > DEVICE_EXPIRY_TIME:
            expired_devices.append(device_id)
    
    for device_id in expired_devices:
        del devices_db[device_id]
    
    if expired_devices:
        logger.info(f"Removed {len(expired_devices)} expired devices")
        save_devices_db()
    
    last_cleanup_time = current_time

def update_device_db(device):
    device_id = device['id']
    
    # Check if device exists in database
    if device_id in devices_db:
        # Update existing device
        existing_device = devices_db[device_id]
        
        # Check if location has changed significantly
        if 'location' in device and 'location' in existing_device:
            new_lat = device['location'].get('lat') or device['location'].get('latitude')
            new_lng = device['location'].get('lng') or device['location'].get('longitude')
            old_lat = existing_device['location'].get('lat') or existing_device['location'].get('latitude')
            old_lng = existing_device['location'].get('lng') or existing_device['location'].get('longitude')
            
            # Only update if location has changed by more than 0.0001 degrees (about 10 meters)
            location_changed = (
                abs(float(new_lat) - float(old_lat)) > 0.0001 or 
                abs(float(new_lng) - float(old_lng)) > 0.0001
            )
            
            if location_changed:
                logger.info(f"Device {device_id} location changed")
                existing_device['location'] = device['location']
        
        # Update last seen time
        existing_device['last_seen'] = device['last_seen']
        
        # Update power level
        if 'power' in device:
            existing_device['power'] = device['power']
        
        # Update frequency if it changed
        if 'frequency' in device and device['frequency'] != existing_device.get('frequency'):
            existing_device['frequency'] = device['frequency']
        
        # Update whitelisted status
        existing_device['whitelisted'] = device['whitelisted']
        
    else:
        # Add new device to database
        devices_db[device_id] = device
        logger.info(f"Added new device to database: {device_id}")
    
    # Save the database periodically
    if len(devices_db) % 5 == 0:  # Save after every 5 new devices
        save_devices_db()

# Load whitelist and devices database on startup
load_whitelist()
verify_whitelist()
load_devices_db()

# WebSocket connections
connections = []

# Serve index.html
@app.get("/", response_class=HTMLResponse)
async def get():
    with open("static/index.html", "r") as f:
        return HTMLResponse(content=f.read())

@app.get("/api/devices")
async def get_devices():
    try:
        # Run cleanup to remove expired devices
        cleanup_expired_devices()
        
        # Capture RF data
        samples = rf_monitor.capture_samples()
        if samples is not None:
            spectrum_data = rf_monitor.analyze_spectrum(samples)
            
            # Process spectrum data to identify potential devices
            current_devices = []
            if spectrum_data and 'devices' in spectrum_data:
                # Get current GPS location for the monitoring station
                monitoring_station_location = None
                if gps_module.is_connected():
                    gps_location = gps_module.get_location()
                    if gps_location:
                        # Ensure all numeric values are converted to float
                        try:
                            latitude = float(gps_location['latitude'])
                            longitude = float(gps_location['longitude'])
                            altitude = float(gps_location.get('altitude', 0))
                            num_satellites = str(gps_location.get('num_satellites', 0))  # Keep as string for display
                            hdop = float(gps_location.get('hdop', 0))
                            
                            monitoring_station_location = {
                                "latitude": latitude,
                                "longitude": longitude,
                                "altitude": altitude,
                                "num_satellites": num_satellites,
                                "hdop": hdop
                            }
                        except Exception as e:
                            logger.error(f"Error processing GPS data: {e}")
                
                # Use the devices directly from the spectrum_data
                for device in spectrum_data['devices']:
                    # Check if device is in whitelist and update accordingly
                    device_id = device['id']
                    device['whitelisted'] = device_id in whitelist
                    if device_id in whitelist:
                        device.update(whitelist[device_id])
                    
                    # Add current timestamp
                    device['last_seen'] = datetime.now().isoformat()
                    
                    # Add location information to the device (based on monitoring station)
                    if monitoring_station_location:
                        # Add a small random offset to make devices appear around the monitoring station
                        # This simulates different device locations
                        lat_offset = (random.random() - 0.5) * 0.005  # ~500m radius
                        lng_offset = (random.random() - 0.5) * 0.005
                        
                        device['location'] = {
                            "latitude": monitoring_station_location["latitude"] + lat_offset,
                            "longitude": monitoring_station_location["longitude"] + lng_offset
                        }
                    else:
                        # If no GPS, use a default location
                        device['location'] = {
                            "latitude": 38.897957,  # Default to a location
                            "longitude": -77.036560
                        }
                    
                    # Add to current devices list
                    current_devices.append(device)
            
            # Update devices database with currently detected devices
            for device in current_devices:
                update_device_db(device)
            
            # Get current GPS location for the monitoring station
            monitoring_station_location = None
            if gps_module.is_connected():
                gps_location = gps_module.get_location()
                if gps_location:
                    # Ensure all numeric values are converted to float
                    try:
                        latitude = float(gps_location['latitude'])
                        longitude = float(gps_location['longitude'])
                        altitude = float(gps_location.get('altitude', 0))
                        num_satellites = str(gps_location.get('num_satellites', 0))  # Keep as string for display
                        hdop = float(gps_location.get('hdop', 0))
                        
                        monitoring_station_location = {
                            "latitude": latitude,
                            "longitude": longitude,
                            "altitude": altitude,
                            "num_satellites": num_satellites,
                            "hdop": hdop
                        }
                    except Exception as e:
                        logger.error(f"Error processing GPS data: {e}")
            
            # Get all devices from the database (includes current and previously seen devices)
            all_devices = list(devices_db.values())
            
            # Prepare response
            response = {
                "devices": all_devices,
                "spectrum": spectrum_data.get('spectrum', []) if spectrum_data else [],
                "monitoring_station": monitoring_station_location
            }
            
            return response
        else:
            return {"error": "Failed to capture RF samples"}
    except Exception as e:
        logger.error(f"Error in get_devices: {e}")
        return {"error": str(e)}

@app.post("/api/whitelist/{device_id}")
async def whitelist_device(device_id: str, device: Device):
    try:
        # Create or update the device in the whitelist
        whitelist[device_id] = {
            "name": device.name,
            "type": device.type,
            "frequency": device.frequency,
            "first_seen": device.first_seen or datetime.now().isoformat(),
            "last_seen": datetime.now().isoformat(),
            "whitelisted": True
        }
        
        # Save whitelist to file after adding a device
        save_whitelist()
        
        # Also update the device in the devices_db if it exists
        if device_id in devices_db:
            devices_db[device_id]["whitelisted"] = True
            devices_db[device_id]["name"] = device.name
            devices_db[device_id]["type"] = device.type
            save_devices_db()
        
        logger.info(f"Device {device_id} added to whitelist")
        return {"status": "success", "message": f"Device {device_id} added to whitelist"}
    except Exception as e:
        logger.error(f"Error adding device {device_id} to whitelist: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to add device to whitelist: {str(e)}")

@app.delete("/api/whitelist/{device_id}")
async def remove_from_whitelist(device_id: str):
    try:
        if device_id in whitelist:
            # Remove from whitelist
            del whitelist[device_id]
            
            # Save whitelist to file after removing a device
            save_whitelist()
            
            # Update the device in devices_db if it exists
            if device_id in devices_db:
                devices_db[device_id]["whitelisted"] = False
                save_devices_db()
            
            logger.info(f"Device {device_id} removed from whitelist")
            return {"status": "success", "message": f"Device {device_id} removed from whitelist"}
        else:
            logger.warning(f"Attempt to remove non-existent device {device_id} from whitelist")
            raise HTTPException(status_code=404, detail=f"Device {device_id} not found in whitelist")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error removing device {device_id} from whitelist: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to remove device from whitelist: {str(e)}")

@app.get("/api/whitelist")
async def get_whitelist():
    try:
        # Ensure whitelist is loaded
        if not whitelist and os.path.exists(WHITELIST_FILE):
            load_whitelist()
        return {"whitelist": whitelist}
    except Exception as e:
        logger.error(f"Error retrieving whitelist: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to retrieve whitelist: {str(e)}")

@app.get("/api/monitoring_station")
async def get_monitoring_station():
    """Get the current location of the monitoring station"""
    try:
        # Get current GPS location
        location = get_current_gps_location()
        
        # Add additional information about the GPS module
        return {
            "location": location,
            "using_real_gps": gps_module.is_using_real_gps(),
            "is_connected": gps_module.is_connected()
        }
    except Exception as e:
        logger.error(f"Error getting monitoring station location: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    connections.append(websocket)
    logger.info(f"WebSocket client connected. Total connections: {len(connections)}")
    
    try:
        while True:
            # Wait for a message (this is just to keep the connection alive)
            # We don't actually use the received message for anything
            await websocket.receive_text()
    except WebSocketDisconnect:
        connections.remove(websocket)
        logger.info(f"WebSocket client disconnected. Remaining connections: {len(connections)}")

async def broadcast_data():
    """Broadcast RF data to all connected WebSocket clients"""
    while True:
        if connections:  # Only process if there are active connections
            try:
                # Run cleanup to remove expired devices
                cleanup_expired_devices()
                
                # Capture RF data
                samples = rf_monitor.capture_samples()
                if samples is not None:
                    spectrum_data = rf_monitor.analyze_spectrum(samples)
                    
                    # Process spectrum data to identify potential devices
                    current_devices = []
                    if spectrum_data and 'devices' in spectrum_data:
                        # Get current GPS location for the monitoring station
                        monitoring_station_location = None
                        if gps_module.is_connected():
                            gps_location = gps_module.get_location()
                            if gps_location:
                                # Ensure all numeric values are converted to float
                                try:
                                    latitude = float(gps_location['latitude'])
                                    longitude = float(gps_location['longitude'])
                                    altitude = float(gps_location.get('altitude', 0))
                                    num_satellites = str(gps_location.get('num_satellites', 0))
                                    hdop = float(gps_location.get('hdop', 0))
                                    
                                    monitoring_station_location = {
                                        "latitude": latitude,
                                        "longitude": longitude,
                                        "altitude": altitude,
                                        "num_satellites": num_satellites,
                                        "hdop": hdop
                                    }
                                except Exception as e:
                                    logger.error(f"Error processing GPS data: {e}")
                        
                        # Use the devices directly from the spectrum_data
                        for device in spectrum_data['devices']:
                            # Check if device is in whitelist and update accordingly
                            device_id = device['id']
                            device['whitelisted'] = device_id in whitelist
                            if device_id in whitelist:
                                device.update(whitelist[device_id])
                            
                            # Add current timestamp
                            device['last_seen'] = datetime.now().isoformat()
                            
                            # Add location information to the device (based on monitoring station)
                            if monitoring_station_location:
                                # Add a small random offset to make devices appear around the monitoring station
                                # This simulates different device locations
                                lat_offset = (random.random() - 0.5) * 0.005  # ~500m radius
                                lng_offset = (random.random() - 0.5) * 0.005
                                
                                device['location'] = {
                                    "latitude": monitoring_station_location["latitude"] + lat_offset,
                                    "longitude": monitoring_station_location["longitude"] + lng_offset
                                }
                            else:
                                # If no GPS, use a default location
                                device['location'] = {
                                    "latitude": 38.897957,  # Default to a location
                                    "longitude": -77.036560
                                }
                            
                            # Add to current devices list
                            current_devices.append(device)
                        
                        # Update devices database with currently detected devices
                        for device in current_devices:
                            update_device_db(device)
                        
                        # Get all devices from the database (includes current and previously seen devices)
                        all_devices = list(devices_db.values())
                        
                        # Prepare data to broadcast
                        data = {
                            "devices": all_devices,
                            "spectrum": spectrum_data.get('spectrum', []) if spectrum_data else [],
                            "monitoring_station": monitoring_station_location
                        }
                        
                        # Broadcast to all connected clients
                        for connection in connections:
                            try:
                                await connection.send_json(data)
                            except Exception as e:
                                logger.error(f"Error sending data to WebSocket client: {e}")
                                # Remove failed connection
                                if connection in connections:
                                    connections.remove(connection)
            except Exception as e:
                logger.error(f"Error in broadcast_data: {e}")
        
        # Wait before next update
        await asyncio.sleep(1)

async def periodic_save():
    """Periodically save whitelist and devices database to ensure data persistence"""
    while True:
        try:
            # Save whitelist and devices_db every 5 minutes
            save_whitelist()
            save_devices_db()
            logger.info("Periodic save of whitelist and devices database completed")
        except Exception as e:
            logger.error(f"Error in periodic save: {e}")
        
        # Wait for 5 minutes
        await asyncio.sleep(300)

@app.on_event("startup")
async def startup_event():
    # Load and verify whitelist
    load_whitelist()
    verify_whitelist()
    
    # Start the broadcast task
    asyncio.create_task(broadcast_data())
    # Start the periodic save task
    asyncio.create_task(periodic_save())

@app.on_event("shutdown")
async def shutdown_event():
    # Stop the GPS module when the app shuts down
    if gps_module:
        gps_module.stop()
        logger.info("GPS module stopped during shutdown")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
