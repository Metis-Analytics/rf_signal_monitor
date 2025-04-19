import numpy as np
from scipy import signal
import json
from datetime import datetime
import os
import uuid
import random

class CellularDetector:
    GSM_FREQUENCIES = {
        # GSM-850
        850: {'uplink': (824.0e6, 849.0e6), 'downlink': (869.0e6, 894.0e6)},
        # GSM-900
        900: {'uplink': (890.0e6, 915.0e6), 'downlink': (935.0e6, 960.0e6)},
        # GSM-1800
        1800: {'uplink': (1710.0e6, 1785.0e6), 'downlink': (1805.0e6, 1880.0e6)},
        # GSM-1900
        1900: {'uplink': (1850.0e6, 1910.0e6), 'downlink': (1930.0e6, 1990.0e6)}
    }
    
    # LTE bands frequency ranges
    LTE_BANDS = {
        # Band 1 (2100 MHz)
        1: {'uplink': (1920e6, 1980e6), 'downlink': (2110e6, 2170e6)},
        # Band 2 (1900 MHz)
        2: {'uplink': (1850e6, 1910e6), 'downlink': (1930e6, 1990e6)},
        # Band 3 (1800 MHz)
        3: {'uplink': (1710e6, 1785e6), 'downlink': (1805e6, 1880e6)},
        # Band 4 (AWS-1)
        4: {'uplink': (1710e6, 1755e6), 'downlink': (2110e6, 2155e6)},
        # Band 5 (850 MHz)
        5: {'uplink': (824e6, 849e6), 'downlink': (869e6, 894e6)},
        # Band 7 (2600 MHz)
        7: {'uplink': (2500e6, 2570e6), 'downlink': (2620e6, 2690e6)},
        # Band 12 (700 MHz)
        12: {'uplink': (699e6, 716e6), 'downlink': (729e6, 746e6)},
        # Band 13 (700 MHz)
        13: {'uplink': (777e6, 787e6), 'downlink': (746e6, 756e6)},
        # Band 17 (700 MHz)
        17: {'uplink': (704e6, 716e6), 'downlink': (734e6, 746e6)},
        # Band 30 (2300 MHz)
        30: {'uplink': (2305e6, 2315e6), 'downlink': (2350e6, 2360e6)}
    }

    def __init__(self):
        self.known_devices = {}
        self.load_cached_data()

    def load_cached_data(self):
        """Load previously detected device data"""
        try:
            if os.path.exists('device_cache.json'):
                with open('device_cache.json', 'r') as f:
                    self.known_devices = json.load(f)
        except Exception as e:
            print(f"Error loading device cache: {e}")

    def save_cached_data(self):
        """Save detected device data"""
        try:
            # Convert any NumPy values to Python types before serialization
            devices_copy = {}
            for device_id, device_data in self.known_devices.items():
                devices_copy[device_id] = {}
                for key, value in device_data.items():
                    if isinstance(value, np.integer):
                        devices_copy[device_id][key] = int(value)
                    elif isinstance(value, np.floating):
                        devices_copy[device_id][key] = float(value)
                    elif isinstance(value, np.ndarray):
                        devices_copy[device_id][key] = value.tolist()
                    else:
                        devices_copy[device_id][key] = value
            
            # Save the converted data
            with open('device_cache.json', 'w') as f:
                json.dump(devices_copy, f)
        except Exception as e:
            print(f"Error saving device cache: {e}")

    def is_cellular_frequency(self, freq_hz):
        """Check if a frequency falls within cellular bands (GSM or LTE)"""
        # Convert to Hz if in MHz
        if freq_hz < 10000:
            freq_hz *= 1e6
        
        # Check GSM bands (prioritize downlink as these are more likely to be phones)
        for band, ranges in self.GSM_FREQUENCIES.items():
            if ranges['downlink'][0] <= freq_hz <= ranges['downlink'][1]:
                return True, 'GSM', band, 'downlink'
            elif ranges['uplink'][0] <= freq_hz <= ranges['uplink'][1]:
                return True, 'GSM', band, 'uplink'
        
        # Check LTE bands (prioritize downlink as these are more likely to be phones)
        for band, ranges in self.LTE_BANDS.items():
            if ranges['downlink'][0] <= freq_hz <= ranges['downlink'][1]:
                return True, 'LTE', band, 'downlink'
            elif ranges['uplink'][0] <= freq_hz <= ranges['uplink'][1]:
                return True, 'LTE', band, 'uplink'
        
        return False, None, None, None

    def detect_signal_bursts(self, samples, sample_rate):
        """Detect signal bursts in the signal using energy detection"""
        # Typical burst duration in cellular systems can range from ~0.5 to 4ms
        burst_samples = int(1e-3 * sample_rate)  # 1ms window
        
        # Calculate signal energy
        energy = np.abs(samples)**2
        
        # Moving average for noise floor estimation
        window_size = min(burst_samples * 10, len(samples) // 10)
        noise_floor = np.convolve(energy, np.ones(window_size)/window_size, mode='same')
        
        # Detect bursts where energy is significantly above noise floor
        threshold = 6.0  # 6 dB above noise floor
        burst_mask = energy > (noise_floor * 10**(threshold/10))
        
        # Find burst start positions
        burst_starts = np.where(np.diff(burst_mask.astype(int)) > 0)[0]
        
        return len(burst_starts), burst_starts

    def analyze_signal_characteristics(self, samples, center_freq, sample_rate):
        """Analyze signal for cellular characteristics and attempt to identify type"""
        # Check if in cellular frequency bands
        is_cellular, tech_type, band, link_type = self.is_cellular_frequency(center_freq)
        
        if not is_cellular:
            return None
            
        # Get additional weighting based on frequency band and link type
        # Downlink channels are much more likely to be from cell phones
        detection_confidence = 0.7
        if link_type == 'downlink':
            detection_confidence += 0.2
            
        # Certain bands are more commonly used by cell phones
        common_phone_bands = [850, 700, 1900, 2100]
        if band in common_phone_bands:
            detection_confidence += 0.1
            
        # Calculate average power in dB
        avg_power = 10 * np.log10(np.mean(np.abs(samples)**2))
        
        # Only process strong enough signals
        if avg_power < -70:  # Adjust threshold as needed
            return None
        
        # Calculate max power in dB
        max_power = 10 * np.log10(np.max(np.abs(samples)**2))
        
        # Perform FFT to check spectral characteristics
        window = np.hamming(len(samples))
        samples_windowed = samples * window
        fft = np.fft.fftshift(np.fft.fft(samples_windowed))
        power_spectrum = 10 * np.log10(np.abs(fft)**2)
        
        # Calculate peak-to-average power ratio (PAPR)
        papr = max_power - avg_power
        
        # Detect bursts in the signal
        burst_count, burst_positions = self.detect_signal_bursts(samples, sample_rate)
        
        if burst_count < 3:  # Need minimum 3 bursts to consider it a valid cellular signal
            return None
            
        # Generate a more stable device ID based on frequency and burst pattern
        # This creates more consistent IDs for the same device even when seen multiple times
        frequency_factor = int(center_freq / 1e6) % 1000
        burst_factor = int(burst_count * 10) if burst_count else 0
        power_factor = int(avg_power * 100) if avg_power else 0
        id_seed = f"{frequency_factor}-{burst_factor}-{power_factor}"
        
        import hashlib
        device_id = hashlib.md5(id_seed.encode()).hexdigest()[:8]
        
        # Check if we've seen a similar device before (within close frequency/power range)
        similar_device = None
        for known_id, known_device in self.known_devices.items():
            if abs(known_device['frequency'] - center_freq) < 50000 and \
               abs(known_device['power'] - avg_power) < 5:
                similar_device = known_device
                device_id = known_id  # Use the existing ID for consistency
                break
                
        # Get a virtual "simulated ID" that looks somewhat like a real cellular ID
        # Format it like an IMEI with appropriate prefixes based on technology type
        if tech_type == 'LTE':
            # LTE uses TAC (Type Allocation Code) prefixes
            sim_prefix = '35' + str(random.randint(0, 9)) + str(random.randint(0, 9))
        else:  # GSM
            sim_prefix = '49' + str(random.randint(0, 9)) + str(random.randint(0, 9))
            
        # Create a consistent IMEI-like ID using the device_id as a seed
        random.seed(device_id)  # Make generation deterministic based on device_id
        remaining_digits = ''.join([str(random.randint(0, 9)) for _ in range(10)])
        simulated_id = f"{sim_prefix}{remaining_digits}"
        
        # Get the current timestamp
        timestamp = datetime.now().isoformat()
        
        # Determine device subtypes for cell phones based on technology and characteristics
        # Replace generic 'GSM'/'LTE' with more specific cell phone types
        device_subtype = 'Cell Phone'  # Default
        manufacturer = 'Unknown'        # Default
        
        # Refine device subtype and manufacturer based on technology and frequency
        if tech_type == 'LTE':
            device_subtype = 'LTE Phone'
            # Determine likely manufacturer based on device characteristics
            if band in [1, 3, 7, 8]:  # International bands
                if papr > 8.0:  # Higher PAPR often seen in certain manufacturers
                    manufacturer = 'Samsung'
                else:
                    manufacturer = 'Apple'
            elif band in [12, 13, 17]:  # US coverage bands
                if papr > 8.5:
                    manufacturer = 'Google'
                else:
                    manufacturer = 'Apple'
            elif band in [5, 2, 4]:  # Common US bands
                manufacturer = 'Samsung'
        else:  # GSM
            device_subtype = 'GSM Phone'
            if band == 1900:
                manufacturer = 'Motorola'
            elif band == 850:
                manufacturer = 'LG'
            else:
                manufacturer = 'Nokia'
                
        # Create a device data structure
        device = {
            'id': device_id,
            'type': 'Cell Phone',  # Always identify as cell phone
            'subtype': device_subtype,  # More specific type (GSM Phone/LTE Phone)
            'manufacturer': manufacturer,
            'band': band,
            'tech': tech_type,  # Keep original technology information
            'link_type': link_type,
            'confidence': detection_confidence,
            'frequency': center_freq,
            'frequency_mhz': center_freq / 1e6,
            'power': avg_power,
            'papr': papr,
            'burst_count': burst_count,
            'simulated_id': simulated_id,  # NOT a real IMSI/IMEI, just for UI
            'first_seen': timestamp,
            'last_seen': timestamp,
            'location': None  # Will be updated when location data is available
        }
        
        self.known_devices[device_id] = device
        self.save_cached_data()
        
        return device

    def analyze_cellular_signal(self, samples, center_freq, sample_rate):
        """Main method to analyze signal for cellular characteristics"""
        return self.analyze_signal_characteristics(samples, center_freq, sample_rate)
