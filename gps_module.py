import serial.tools.list_ports
from serial import Serial, SerialException
import pynmea2
import threading
import time
import logging
import os
import random

class GPSModule:
    def __init__(self, port=None, baudrate=4800, simulation_mode=False, force_real=False):
        """
        Initialize the GPS module.
        
        Args:
            port (str): Serial port for the GPS device (e.g., 'COM5' on Windows)
            baudrate (int): Baud rate for the GPS device (default: 4800)
            simulation_mode (bool): If True, generate simulated GPS data when real GPS is unavailable
            force_real (bool): If True, will only use real GPS and not fall back to simulation
        """
        self.port = port
        self.baudrate = baudrate
        self.serial_conn = None
        self.running = False
        self.thread = None
        self.current_location = None
        self.last_update = None
        self.logger = logging.getLogger("gps_module")
        self.simulation_mode = simulation_mode
        self.force_real = force_real
        self.using_real_gps = False
        
        # Set up logging
        logging.basicConfig(level=logging.INFO)
    
    def start(self):
        """Start reading GPS data in a separate thread"""
        if self.running:
            return
        
        self.running = True
        self.thread = threading.Thread(target=self._read_gps)
        self.thread.daemon = True
        self.thread.start()
        
    def stop(self):
        """Stop the GPS reading thread"""
        self.running = False
        if self.thread:
            self.thread.join(timeout=2.0)
        if self.serial_conn and self.serial_conn.is_open:
            self.serial_conn.close()
        self.logger.info("GPS module stopped")
    
    def _read_gps(self):
        """Read GPS data in a separate thread"""
        # If explicitly in simulation mode and not forcing real GPS, go straight to simulation
        if self.simulation_mode and not self.force_real:
            self.logger.info("Starting GPS in simulation mode (explicit)")
            self._run_simulation()
            return
            
        # Try to connect to a real GPS device first
        connected = self._try_connect_real_gps()
        
        # If we couldn't connect to a real GPS and simulation is allowed, fall back to simulation
        if not connected and not self.force_real:
            self.logger.info("Falling back to GPS simulation mode")
            self._run_simulation()
    
    def _try_connect_real_gps(self):
        """Try to connect to a real GPS device"""
        # Common baudrates for GPS devices
        baudrates_to_try = [self.baudrate]  # Start with the specified baudrate
        
        # If the specified baudrate is not one of these common ones, add them to the list
        common_baudrates = [4800, 9600, 38400, 115200]
        for baudrate in common_baudrates:
            if baudrate != self.baudrate:
                baudrates_to_try.append(baudrate)
        
        # Try each baudrate
        for baudrate in baudrates_to_try:
            try:
                self.logger.info(f"Trying to connect to GPS device on {self.port} with baudrate {baudrate}")
                self.serial_conn = Serial(port=self.port, baudrate=baudrate, timeout=1)
                self.logger.info(f"Connected to GPS device on {self.port} with baudrate {baudrate}")
                
                # Try to read data for a few seconds to see if we get valid NMEA sentences
                start_time = time.time()
                valid_data_found = False
                
                while self.running and (time.time() - start_time) < 10:  # Try for 10 seconds
                    try:
                        line = self.serial_conn.readline().decode('ascii', errors='replace').strip()
                        if line:
                            self.logger.debug(f"Raw GPS data: {line}")
                            
                        if line.startswith('$'):
                            try:
                                msg = pynmea2.parse(line)
                                self.logger.debug(f"Parsed NMEA message: {msg}")
                                valid_data_found = True
                                
                                # If we found a valid message, start processing GPS data
                                self.using_real_gps = True
                                self._process_gps_data()
                                return True
                            except pynmea2.ParseError as pe:
                                self.logger.debug(f"NMEA parse error: {pe} for line: {line}")
                    except UnicodeDecodeError as ude:
                        self.logger.debug(f"Unicode decode error: {ude}")
                    except Exception as e:
                        self.logger.error(f"Error reading GPS data: {e}")
                        time.sleep(0.1)
                
                if not valid_data_found:
                    self.logger.info(f"No valid NMEA data found with baudrate {baudrate}")
                    self.serial_conn.close()
            except SerialException as e:
                self.logger.error(f"Error connecting to GPS device with baudrate {baudrate}: {e}")
                continue
        
        self.logger.error("Could not connect to a real GPS device")
        return False
    
    def _process_gps_data(self):
        """Process GPS data from the connected device"""
        try:
            while self.running:
                try:
                    line = self.serial_conn.readline().decode('ascii', errors='replace').strip()
                    if line:
                        self.logger.debug(f"Raw GPS data: {line}")
                        
                    if line.startswith('$'):
                        try:
                            msg = pynmea2.parse(line)
                            
                            # Process different NMEA message types
                            if isinstance(msg, pynmea2.GGA):
                                self.logger.info(f"GGA message received: lat={msg.latitude}, lon={msg.longitude}")
                                if msg.latitude and msg.longitude:
                                    try:
                                        self.current_location = {
                                            'latitude': float(msg.latitude),
                                            'longitude': float(msg.longitude),
                                            'altitude': float(msg.altitude) if msg.altitude else 0.0,
                                            'num_satellites': str(msg.num_sats) if msg.num_sats else '0',
                                            'hdop': float(msg.horizontal_dil) if msg.horizontal_dil else 0.0,
                                            'timestamp': msg.timestamp,
                                            'simulated': False
                                        }
                                        self.last_update = time.time()
                                        self.logger.info(f"GPS location updated: {self.current_location}")
                                    except (ValueError, TypeError) as e:
                                        self.logger.error(f"Error converting GGA data: {e}, raw data: {msg}")
                            elif isinstance(msg, pynmea2.RMC) and not self.current_location:
                                # Use RMC as a fallback if we don't have GGA data
                                self.logger.info(f"RMC message received: lat={msg.latitude}, lon={msg.longitude}")
                                if msg.latitude and msg.longitude:
                                    try:
                                        self.current_location = {
                                            'latitude': float(msg.latitude),
                                            'longitude': float(msg.longitude),
                                            'altitude': 0.0,  # RMC doesn't have altitude
                                            'num_satellites': '0',  # RMC doesn't have satellite count
                                            'hdop': 0.0,  # RMC doesn't have HDOP
                                            'timestamp': msg.timestamp,
                                            'simulated': False
                                        }
                                        self.last_update = time.time()
                                        self.logger.info(f"GPS location updated from RMC: {self.current_location}")
                                    except (ValueError, TypeError) as e:
                                        self.logger.error(f"Error converting RMC data: {e}, raw data: {msg}")
                        except pynmea2.ParseError as pe:
                            self.logger.error(f"NMEA parse error: {pe} for line: {line}")
                except UnicodeDecodeError as ude:
                    self.logger.error(f"Unicode decode error: {ude}")
                except Exception as e:
                    self.logger.error(f"Error reading GPS data: {e}")
                    time.sleep(1)
        except serial.SerialException as e:
            self.logger.error(f"Error with GPS device connection: {e}")
            if not self.force_real:
                self.logger.info("Switching to simulation mode after connection error")
                self._run_simulation()
        finally:
            if self.serial_conn and self.serial_conn.is_open:
                self.serial_conn.close()
    
    def _run_simulation(self):
        """Run GPS simulation"""
        # Simulate GPS data - using a more realistic starting location
        self.current_location = {
            'latitude': 39.8283,  # Approximate center of US
            'longitude': -98.5795,  # Approximate center of US
            'altitude': 10.0,
            'num_satellites': '8',
            'hdop': 1.2,
            'timestamp': time.time(),
            'simulated': True
        }
        self.last_update = time.time()
        self.logger.info(f"Simulated GPS location initialized: {self.current_location}")
        
        # Simulate small movements over time
        while self.running:
            time.sleep(1)
            # Add some random movement to make it more realistic
            self.current_location['latitude'] += random.uniform(-0.0001, 0.0001)
            self.current_location['longitude'] += random.uniform(-0.0001, 0.0001)
            self.current_location['num_satellites'] = str(max(4, min(12, int(self.current_location['num_satellites']) + random.randint(-1, 1))))
            self.current_location['hdop'] = max(0.8, min(2.5, self.current_location['hdop'] + random.uniform(-0.1, 0.1)))
            self.last_update = time.time()
            self.logger.debug(f"Simulated GPS location updated: {self.current_location}")
    
    def get_location(self):
        """
        Get the current GPS location.
        
        Returns:
            dict: Dictionary containing latitude, longitude, altitude, etc.
                  or None if no location data is available
        """
        return self.current_location
    
    def is_connected(self):
        """Check if the GPS device is connected and providing data"""
        # If in simulation mode, always return True
        if self.simulation_mode and not self.using_real_gps:
            return True
            
        if not self.current_location:
            return False
        
        # Consider the connection active if we've received data in the last 5 seconds
        if self.last_update and (time.time() - self.last_update) <= 5:
            return True
        
        return False
    
    def is_using_real_gps(self):
        """Check if we're using a real GPS device or simulation"""
        return self.using_real_gps

# For testing the module directly
if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Test GPS module")
    parser.add_argument("--port", type=str, required=True, help="Serial port for GPS device")
    parser.add_argument("--baudrate", type=int, default=4800, help="Baud rate for GPS device")
    parser.add_argument("--simulation", action="store_true", help="Use simulation mode")
    parser.add_argument("--force-real", action="store_true", help="Force use of real GPS only (no simulation fallback)")
    
    args = parser.parse_args()
    
    gps = GPSModule(port=args.port, baudrate=args.baudrate, simulation_mode=args.simulation, force_real=args.force_real)
    gps.start()
    
    try:
        print("GPS module started. Press Ctrl+C to exit.")
        while True:
            location = gps.get_location()
            if location:
                print(f"Location: {location}")
                print(f"Using real GPS: {gps.is_using_real_gps()}")
            else:
                print("Waiting for GPS data...")
            time.sleep(1)
    except KeyboardInterrupt:
        print("Stopping GPS module...")
    finally:
        gps.stop()
