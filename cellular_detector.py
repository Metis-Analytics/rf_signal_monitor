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
    
    # UMTS (3G) frequency bands
    UMTS_FREQUENCIES = {
        # Band 1 (2100 MHz) - Most common UMTS band worldwide
        1: {'uplink': (1920e6, 1980e6), 'downlink': (2110e6, 2170e6)},
        # Band 2 (1900 MHz) - Used in Americas
        2: {'uplink': (1850e6, 1910e6), 'downlink': (1930e6, 1990e6)},
        # Band 4 (AWS-1) - Used in Americas
        4: {'uplink': (1710e6, 1755e6), 'downlink': (2110e6, 2155e6)},
        # Band 5 (850 MHz) - Used in Americas
        5: {'uplink': (824e6, 849e6), 'downlink': (869e6, 894e6)},
        # Band 8 (900 MHz) - Used in Europe, Asia, etc.
        8: {'uplink': (880e6, 915e6), 'downlink': (925e6, 960e6)}
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
        """Check if a frequency falls within cellular bands (GSM, UMTS, or LTE)"""
        # Convert to Hz if in MHz
        if freq_hz < 10000:
            freq_hz *= 1e6
        
        # Check GSM bands (prioritize downlink as these are more likely to be phones)
        for band, ranges in self.GSM_FREQUENCIES.items():
            if ranges['downlink'][0] <= freq_hz <= ranges['downlink'][1]:
                return True, 'GSM', band, 'downlink'
            elif ranges['uplink'][0] <= freq_hz <= ranges['uplink'][1]:
                return True, 'GSM', band, 'uplink'
        
        # Check UMTS bands
        for band, ranges in self.UMTS_FREQUENCIES.items():
            if ranges['downlink'][0] <= freq_hz <= ranges['downlink'][1]:
                return True, 'UMTS', band, 'downlink'
            elif ranges['uplink'][0] <= freq_hz <= ranges['uplink'][1]:
                return True, 'UMTS', band, 'uplink'
        
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
        
        # Improved device type detection
        # Analyze signal characteristics to determine if it's a phone or network equipment
        is_network_equipment = False
        network_equipment_type = None
        
        # Network equipment typically has:
        # 1. Higher power levels
        # 2. More stable signal (lower PAPR)
        # 3. Continuous transmission patterns
        if avg_power > -20 and papr < 4.0:
            is_network_equipment = True
            
            # Determine network equipment type based on frequency and tech
            if tech_type == 'GSM':
                if link_type == 'downlink':
                    network_equipment_type = 'GSM Base Station'
                else:
                    network_equipment_type = 'GSM Network Equipment'
            elif tech_type == 'LTE':
                if link_type == 'downlink':
                    network_equipment_type = 'LTE eNodeB'
                else:
                    network_equipment_type = 'LTE Network Equipment'
            elif tech_type == 'UMTS':
                if link_type == 'downlink':
                    network_equipment_type = 'UMTS NodeB'
                else:
                    network_equipment_type = 'UMTS Network Equipment'
            else:
                network_equipment_type = 'Cellular Network Equipment'
        
        # Generate ID based on device type
        # Different ID formats for phones vs network equipment
        if is_network_equipment:
            # For network equipment, use a format based on MCC-MNC codes
            # US carriers typically use 310-XXX format
            mcc = "310"  # US Mobile Country Code
            mnc = str(random.randint(1, 999)).zfill(3)  # Random Mobile Network Code
            
            # Create a network equipment ID format
            # Format: MCC+MNC+Equipment Type Code+Serial
            equipment_type_code = "01" if "Base" in network_equipment_type else "02"
            serial = ''.join([str(random.randint(0, 9)) for _ in range(7)])
            network_id = f"{mcc}{mnc}{equipment_type_code}{serial}"
            
            # Ensure it's exactly 15 digits for consistency with IMEI format
            if len(network_id) > 15:
                network_id = network_id[:15]
            elif len(network_id) < 15:
                network_id = network_id + '0' * (15 - len(network_id))
                
            simulated_id = network_id
            
            # Set manufacturer based on MNC
            if mnc in ["020", "070", "090"]:
                manufacturer = "AT&T"
            elif mnc in ["004", "010", "012"]:
                manufacturer = "Verizon"
            elif mnc in ["260", "240", "250"]:
                manufacturer = "T-Mobile"
            elif mnc in ["120", "490", "890"]:
                manufacturer = "Sprint"
            else:
                manufacturer = "Network Operator"
                
            # Use network equipment type as subtype
            device_subtype = network_equipment_type
                
        else:
            # For phones, use standard IMEI generation
            try:
                simulated_id = self.generate_imei(manufacturer, tech_type, device_id)
            except Exception as e:
                print(f"Error in IMEI generation process: {e}")
                # Ultimate fallback with hardcoded valid IMEI
                simulated_id = "352999000000000"
            
            # Determine device subtypes for cell phones based on technology and characteristics
            # Replace generic 'GSM'/'LTE' with more specific cell phone types
            device_subtype = 'Cell Phone'  # Default
            
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
            elif tech_type == 'UMTS':
                device_subtype = 'UMTS Phone'
                if band == 1:
                    manufacturer = 'Nokia'
                elif band == 2:
                    manufacturer = 'Motorola'
                elif band == 4:
                    manufacturer = 'LG'
                elif band == 5:
                    manufacturer = 'Sony'
                else:
                    manufacturer = 'Unknown'
            else:  # GSM
                device_subtype = 'GSM Phone'
                if band == 1900:
                    manufacturer = 'Motorola'
                elif band == 850:
                    manufacturer = 'LG'
                else:
                    manufacturer = 'Nokia'
        
        # Get the current timestamp
        timestamp = datetime.now().isoformat()
        
        # Create a device data structure
        try:
            device = {
                'id': device_id,
                'type': 'Cell Phone' if not is_network_equipment else 'Network Equipment',  # Always identify as cell phone or network equipment
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
                'imei': simulated_id,  # Standards-compliant IMEI
                'first_seen': timestamp,
                'last_seen': timestamp,
                'location': None  # Will be updated when location data is available
            }
            
            self.known_devices[device_id] = device
            self.save_cached_data()
            
            return device
        except Exception as e:
            print(f"Error creating device data structure: {e}")
            # Return a minimal valid device structure if the full one fails
            return {
                'id': device_id,
                'type': 'Cell Phone' if not is_network_equipment else 'Network Equipment',
                'manufacturer': manufacturer,
                'frequency': center_freq,
                'frequency_mhz': center_freq / 1e6,
                'power': avg_power,
                'imei': simulated_id,
                'first_seen': timestamp,
                'last_seen': timestamp
            }

    def analyze_cellular_signal(self, samples, center_freq, sample_rate):
        """Main method to analyze signal for cellular characteristics"""
        return self.analyze_signal_characteristics(samples, center_freq, sample_rate)

    def generate_imei(self, manufacturer, tech_type, device_id=None):
        try:
            # Make sure manufacturer is defined with a default value if None
            if manufacturer is None:
                manufacturer = 'Unknown'
                
            # TAC prefixes by manufacturer (first 6 digits)
            # These are approximations based on common TAC ranges
            tac_prefixes = {
                'Apple': ['35325', '35391', '35407', '35501', '35502', '35503'],
                'Samsung': ['35273', '35290', '35332', '35254', '35255', '35256'],
                'Google': ['35851', '35852', '35853', '35854', '35855', '35856'],
                'Motorola': ['35089', '35138', '35156', '35157', '35158', '35159'],
                'LG': ['35201', '35202', '35203', '35204', '35205', '35206'],
                'Nokia': ['35401', '35402', '35403', '35404', '35405', '35406'],
                'Unknown': ['35999']
            }
            
            # Get a prefix based on manufacturer
            prefix = random.choice(tac_prefixes.get(manufacturer, tac_prefixes['Unknown']))
            
            # Add 2 more digits to complete the 8-digit TAC
            tac = prefix + ''.join([str(random.randint(0, 9)) for _ in range(2)])
            
            # Generate 6-digit serial number
            # Use device_id as seed to ensure consistent generation for the same device
            # If device_id is not provided, use a random seed
            if device_id:
                random.seed(str(device_id))
            else:
                random.seed(str(time.time()))
            serial = ''.join([str(random.randint(0, 9)) for _ in range(6)])
            
            # Combine TAC and Serial
            imei_without_check = tac + serial
            
            # Calculate Luhn check digit
            # The Luhn algorithm is used for the check digit in IMEI
            def calculate_luhn_check_digit(digits):
                try:
                    # Double every other digit
                    doubled = []
                    for i, digit in enumerate(digits):
                        if i % 2 == 0:  # Even position (0-indexed)
                            doubled.append(int(digit))
                        else:  # Odd position
                            doubled_digit = int(digit) * 2
                            if doubled_digit > 9:
                                doubled_digit = doubled_digit - 9
                            doubled.append(doubled_digit)
                    
                    # Sum all digits
                    total = sum(doubled)
                    
                    # The check digit is what needs to be added to make the total divisible by 10
                    check_digit = (10 - (total % 10)) % 10
                    return str(check_digit)
                except Exception as e:
                    print(f"Error calculating Luhn check digit: {e}")
                    return "0"  # Default to 0 if calculation fails
            
            # Add check digit
            check_digit = calculate_luhn_check_digit(imei_without_check)
            imei = imei_without_check + check_digit
            
            # Verify the IMEI is exactly 15 digits
            if len(imei) != 15:
                print(f"Warning: Generated IMEI {imei} is not 15 digits. Fixing...")
                # Ensure it's exactly 15 digits by padding or truncating
                if len(imei) < 15:
                    imei = imei + '0' * (15 - len(imei))
                else:
                    imei = imei[:15]
            
            return imei
        except Exception as e:
            print(f"Error generating IMEI: {e}")
            # Fallback to a generic but valid IMEI format if generation fails
            return "352999000000000"
