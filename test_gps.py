import argparse
from gps_module import GPSModule
import time
import logging

# Set up logging
logging.basicConfig(level=logging.DEBUG)  # Set to DEBUG level to see more information
logger = logging.getLogger("test_gps")

def main():
    parser = argparse.ArgumentParser(description="Test GPS module")
    parser.add_argument("--port", type=str, default="COM5", help="Serial port for GPS device (e.g., COM5 for G-Mouse)")
    parser.add_argument("--baudrate", type=int, default=4800, help="Baud rate for GPS device")
    parser.add_argument("--timeout", type=int, default=60, help="Timeout in seconds to wait for GPS data")
    parser.add_argument("--simulate", action="store_true", help="Use simulation mode instead of real GPS")
    
    args = parser.parse_args()
    
    if args.simulate:
        logger.info("Starting GPS test in SIMULATION mode")
        test_simulation_mode()
    else:
        logger.info(f"Starting GPS test on port {args.port} with baudrate {args.baudrate}")
        test_real_gps(args.port, args.baudrate, args.timeout)

def test_real_gps(port, baudrate, timeout):
    """Test with a real GPS device"""
    # Initialize GPS module
    gps = GPSModule(port=port, baudrate=baudrate)
    
    # Start GPS module
    gps.start()
    
    logger.info(f"Waiting up to {timeout} seconds for GPS data...")
    logger.info(f"Using port: {port} with baudrate: {baudrate}")
    logger.info("If no data appears, the GPS device might need to be outside to acquire a satellite signal")
    
    # Wait for GPS data
    start_time = time.time()
    try:
        data_received = False
        while (time.time() - start_time) < timeout:
            location = gps.get_location()
            if location:
                data_received = True
                logger.info("GPS data received!")
                logger.info(f"Latitude: {location['latitude']}, Longitude: {location['longitude']}")
                logger.info(f"Altitude: {location['altitude']} meters")
                logger.info(f"Satellites: {location['num_satellites']}, HDOP: {location['hdop']}")
                logger.info(f"Timestamp: {location['timestamp']}")
                logger.info(f"Is connected: {gps.is_connected()}")
                logger.info("-" * 50)
                time.sleep(5)  # Wait 5 seconds before getting the next reading
            else:
                logger.info("Waiting for GPS data... (Move the device to a window or outdoors for better signal)")
                time.sleep(1)
        
        if not data_received:
            logger.error(f"No GPS data received after {timeout} seconds")
            logger.info("Possible issues:")
            logger.info("1. GPS device needs to be outdoors to acquire satellite signal")
            logger.info("2. Incorrect port or baudrate")
            logger.info("3. GPS device not powered or connected properly")
            logger.info("4. Try a different baudrate (common values: 4800, 9600, 38400)")
            
            # Ask if user wants to try simulation mode
            logger.info("Would you like to try simulation mode instead? (y/n)")
            response = input().lower()
            if response == 'y':
                test_simulation_mode()
    except KeyboardInterrupt:
        logger.info("Test interrupted by user")
    finally:
        # Stop GPS module
        gps.stop()
        logger.info("GPS module stopped")

def test_simulation_mode():
    """Test with simulated GPS data"""
    # Initialize GPS module in simulation mode
    gps = GPSModule(port="NONE", simulation_mode=True)
    
    # Start GPS module
    gps.start()
    
    logger.info("Starting GPS simulation mode test...")
    
    # Wait for simulated GPS data
    try:
        for i in range(10):  # Get 10 readings
            location = gps.get_location()
            if location:
                logger.info(f"SIMULATED GPS data #{i+1}:")
                logger.info(f"Latitude: {location['latitude']}, Longitude: {location['longitude']}")
                logger.info(f"Altitude: {location['altitude']} meters")
                logger.info(f"Satellites: {location['num_satellites']}, HDOP: {location['hdop']}")
                logger.info(f"Timestamp: {location['timestamp']}")
                logger.info(f"Is connected: {gps.is_connected()}")
                logger.info(f"Is simulation: {gps.simulation_mode}")
                logger.info("-" * 50)
            time.sleep(1)
    except KeyboardInterrupt:
        logger.info("Test interrupted by user")
    finally:
        # Stop GPS module
        gps.stop()
        logger.info("GPS simulation stopped")

if __name__ == "__main__":
    main()
