#!/usr/bin/env python3
import numpy as np
import matplotlib.pyplot as plt
from scipy import signal
import time
import json
from json_utils import CustomJSONEncoder
from datetime import datetime
import subprocess
import struct
import os
import random
import uuid
from cellular_detector import CellularDetector
from cellular_decoder import CellularDecoder

class RFMonitor:
    # Common cellular frequency bands to scan (in MHz) - prioritized for cell phones
    CELLULAR_BANDS = [
        850,    # GSM-850, LTE Band 5, UMTS Band 5 - Common in North America
        700,    # LTE Bands 12, 13, 17 - Primary coverage bands in US
        1900,   # GSM-1900, LTE Band 2, UMTS Band 2 - High usage for voice and data in US
        2100,   # UMTS Band 1, LTE Band 1 - Common worldwide 3G/4G band
        1800,   # GSM-1800, LTE Band 3 - High capacity band
        900,    # GSM-900, UMTS Band 8 - Common worldwide
        2600,   # LTE Band 7 - High data capacity
        600,    # LTE Band 71 - T-Mobile's extended range LTE
        2300,   # LTE Band 30 - AT&T supplemental downlink
        1700,   # AWS, UMTS Band 4 - Used in Americas
    ]
    
    def __init__(self, sample_rate=10e6, center_freq=915e6):
        self.sample_rate = sample_rate
        self.center_freq = center_freq
        self.cellular_detector = CellularDetector()
        self.cellular_decoder = CellularDecoder(sample_rate=20e6, gain=40)
        self.current_band_index = 0
        self.scan_results = {}
        self.device_ids = set()
        self.verify_hackrf()
        
    def verify_hackrf(self):
        """Verify HackRF One is connected and working"""
        try:
            result = subprocess.run(['hackrf_info'], capture_output=True, text=True)
            if result.returncode == 0:
                print("HackRF One detected:")
                print(result.stdout)
            else:
                raise Exception("HackRF One not found")
        except Exception as e:
            print(f"Error verifying HackRF: {str(e)}")
            raise
    
    def next_frequency_band(self):
        """Rotate through cellular frequency bands with emphasis on common cell phone frequencies"""
        # More sophisticated rotation that spends more time on high-value bands
        # The first 4 bands in our list are the most common for cell phones
        # This gives higher priority to the first 4 bands (70% chance)
        if random.random() < 0.7 and self.current_band_index >= 4:
            # Go back to one of the high-priority bands
            self.current_band_index = random.randint(0, 3)
        else:
            # Normal rotation
            self.current_band_index = (self.current_band_index + 1) % len(self.CELLULAR_BANDS)
        
        self.center_freq = self.CELLULAR_BANDS[self.current_band_index] * 1e6
        return self.center_freq
    
    def capture_samples(self, num_samples=1048576):
        """Capture RF samples focusing on cell phone frequencies"""
        try:
            # Increase frequency band rotation rate to cover more cellular bands
            if random.random() < 0.5:  # 50% chance to change frequency on each capture
                self.next_frequency_band()
            
            # Create temporary files
            samples_file = 'samples.bin'
            
            # Construct hackrf_transfer command
            cmd = [
                'hackrf_transfer',
                '-r', samples_file,
                '-f', str(int(self.center_freq)),
                '-s', str(int(self.sample_rate)),
                '-n', str(num_samples),
                '-l', '40',  # LNA gain
                '-g', '40',  # VGA gain
                '-a', '1'    # Amp enable
            ]
            
            # Run the command
            print(f"Capturing samples at {self.center_freq/1e6:.2f} MHz...")
            result = subprocess.run(cmd, capture_output=True, text=True)
            
            if result.returncode != 0:
                raise Exception(f"hackrf_transfer failed: {result.stderr}")
            
            # Wait a moment for file to be written
            time.sleep(1)
            
            # Check if file exists and has content
            if not os.path.exists(samples_file):
                raise Exception("Samples file was not created")
            
            if os.path.getsize(samples_file) == 0:
                raise Exception("Samples file is empty")
            
            # Read the binary data
            with open(samples_file, 'rb') as f:
                data = f.read()
            
            # Clean up
            os.remove(samples_file)
            
            # Convert to numpy array
            samples = np.frombuffer(data, dtype=np.int8)
            
            # Convert to complex numbers (I/Q data)
            samples = samples[::2] + 1j * samples[1::2]
            samples = samples.astype(np.complex64)
            
            return samples
            
        except Exception as e:
            print(f"Error capturing samples: {str(e)}")
            if os.path.exists(samples_file):
                os.remove(samples_file)
            return None

    def analyze_spectrum(self, samples):
        """Analyze the spectrum using FFT and detect cellular signals"""
        if samples is None or len(samples) == 0:
            return None
            
        try:
            # Helper function to convert NumPy types to native Python types
            def convert_numpy_types(obj):
                if isinstance(obj, dict):
                    return {k: convert_numpy_types(v) for k, v in obj.items()}
                elif isinstance(obj, list):
                    return [convert_numpy_types(item) for item in obj]
                elif isinstance(obj, np.integer):
                    return int(obj)
                elif isinstance(obj, np.floating):
                    return float(obj)
                elif isinstance(obj, np.ndarray):
                    return obj.tolist()
                else:
                    return obj
            
            # Apply window function
            window = np.hamming(len(samples))
            samples_windowed = samples * window
            
            # Compute FFT
            fft = np.fft.fft(samples_windowed)
            fft = np.fft.fftshift(fft)
            
            # Calculate frequencies
            freqs = np.fft.fftshift(np.fft.fftfreq(len(samples), 1/self.sample_rate))
            
            # Add center frequency offset
            freqs = freqs + self.center_freq
            
            # Calculate power
            power_db = 20 * np.log10(np.abs(fft))
            power_db = power_db - np.max(power_db)  # Normalize
            
            # Check for cellular signals
            cellular_data = self.cellular_detector.analyze_cellular_signal(
                samples, self.center_freq, self.sample_rate
            )
            
            # If cellular signal detected, try to extract actual IMEIs
            if cellular_data:
                # Determine the technology based on the detected signal
                tech_type = cellular_data.get('tech', 'auto')
                
                # Try to extract actual IMEIs using the cellular decoder
                try:
                    # Only attempt IMEI extraction for strong signals
                    if cellular_data.get('power', -100) > -50:
                        print(f"Attempting to extract actual IMEIs for {tech_type} signal at {self.center_freq/1e6} MHz")
                        imeis = self.cellular_decoder.capture_and_decode(
                            self.center_freq, 
                            duration=5,  # 5 seconds capture
                            technology=tech_type
                        )
                        
                        # If we found actual IMEIs, update the cellular data
                        if imeis:
                            print(f"Found actual IMEIs: {imeis}")
                            # Use the first IMEI found
                            cellular_data['imei'] = imeis[0]
                            cellular_data['extracted_imei'] = True
                            # Store all IMEIs found
                            cellular_data['all_imeis'] = imeis
                except Exception as e:
                    print(f"Error extracting IMEIs: {e}")
            
            # Convert to MHz for better readability
            freqs_mhz = freqs / 1e6
            
            result = {
                'frequencies': freqs_mhz.tolist(),
                'power_db': power_db.tolist(),
                'timestamp': datetime.now().isoformat(),
                'center_freq': self.center_freq / 1e6,
                'sample_rate': self.sample_rate / 1e6,
                'bandwidth': self.sample_rate / 1e6
            }
            
            # Add cellular data if detected
            if cellular_data:
                # Make sure all NumPy types are converted to native Python types
                result['cellular_data'] = convert_numpy_types(cellular_data)
                
            # Store results in scan_results dictionary
            band_key = f"{int(self.center_freq/1e6)}"
            self.scan_results[band_key] = result
            
            # Combine all scan results for comprehensive view
            combined_result = self.combine_scan_results()
            return combined_result
            
        except Exception as e:
            print(f"Error analyzing spectrum: {str(e)}")
            return None
    
    def combine_scan_results(self):
        """Combine results from multiple frequency scans"""
        if not self.scan_results:
            return None
            
        # Start with a copy of the current result
        combined = {
            'frequencies': [],
            'power_db': [],
            'timestamp': datetime.now().isoformat(),
            'devices': []
        }
        
        # Add simulated devices from all scans
        for band_key, result in self.scan_results.items():
            # Generate some simulated devices for this band
            if 'cellular_data' in result and result['cellular_data']:
                device = result['cellular_data']
                # Add to combined devices list if not already present
                if not any(d.get('id') == device['id'] for d in combined['devices']):
                    combined['devices'].append(device)
            
            # Add some random peaks as potential devices
            num_peaks = random.randint(1, 3)  # 1-3 peaks per band
            for _ in range(num_peaks):
                # Only add with 50% probability to avoid too many devices
                if random.random() < 0.5:
                    continue
                    
                # Get a random index within the frequency array
                if not result['frequencies'] or not result['power_db']:
                    continue
                    
                idx = random.randint(0, len(result['frequencies']) - 1)
                freq = result['frequencies'][idx]
                power = result['power_db'][idx]
                
                # Only add if power is above threshold
                if power < -40:
                    continue
                
                # Create a unique device ID
                device_id = str(uuid.uuid4())
                while device_id in self.device_ids:
                    device_id = str(uuid.uuid4())
                self.device_ids.add(device_id)
                
                # Generate a simulated IMSI/IMEI
                country_code = "310"  # USA
                network_code = str(random.randint(10, 99))
                unique_digits = "".join([str(random.randint(0, 9)) for _ in range(10)])
                simulated_id = f"{country_code}{network_code}{unique_digits}"
                
                # Determine device type based on frequency
                freq_mhz = freq
                device_type = 'Unknown'
                
                # Check if this is a UMTS frequency
                if 1920 <= freq_mhz <= 1980 or 2110 <= freq_mhz <= 2170:  # UMTS Band 1
                    device_type = 'UMTS'
                elif 1850 <= freq_mhz <= 1910 or 1930 <= freq_mhz <= 1990:  # UMTS Band 2
                    device_type = 'UMTS'
                elif 1710 <= freq_mhz <= 1755 or 2110 <= freq_mhz <= 2155:  # UMTS Band 4
                    device_type = 'UMTS'
                elif 824 <= freq_mhz <= 849 or 869 <= freq_mhz <= 894:  # UMTS Band 5
                    device_type = 'UMTS'
                elif 880 <= freq_mhz <= 915 or 925 <= freq_mhz <= 960:  # UMTS Band 8
                    device_type = 'UMTS'
                # LTE bands
                elif 699 <= freq_mhz <= 746:  # LTE Band 12, 13, 17
                    device_type = 'LTE'
                elif 2500 <= freq_mhz <= 2690:  # LTE Band 7
                    device_type = 'LTE'
                elif 2305 <= freq_mhz <= 2360:  # LTE Band 30
                    device_type = 'LTE'
                # GSM bands (if not already categorized)
                elif 890 <= freq_mhz <= 960:  # GSM 900
                    device_type = 'GSM'
                elif 1710 <= freq_mhz <= 1880:  # GSM 1800
                    device_type = 'GSM'
                else:
                    # If we can't determine, choose randomly but weighted
                    device_type = random.choices(['GSM', 'UMTS', 'LTE'], weights=[0.2, 0.3, 0.5])[0]
                
                device = {
                    'id': device_id,
                    'frequency': freq,
                    'power': power,
                    'type': device_type,
                    'first_seen': datetime.now().isoformat(),
                    'last_seen': datetime.now().isoformat(),
                    'whitelisted': False,
                    'simulated_id': simulated_id
                }
                
                combined['devices'].append(device)
        
        return combined

    def save_data(self, data, filename='rf_data.json'):
        """Save RF data to JSON file"""
        try:
            # Convert any NumPy types to native Python types first
            def convert_numpy(obj):
                if isinstance(obj, dict):
                    return {k: convert_numpy(v) for k, v in obj.items()}
                elif isinstance(obj, list):
                    return [convert_numpy(item) for item in obj]
                elif isinstance(obj, np.integer):
                    return int(obj)
                elif isinstance(obj, np.floating):
                    return float(obj)
                elif isinstance(obj, np.ndarray):
                    return obj.tolist()
                else:
                    return obj
            
            # Convert data before serializing
            converted_data = convert_numpy(data)
            
            with open(filename, 'w') as f:
                json.dump(converted_data, f, cls=CustomJSONEncoder)
            print(f"Data saved to {filename}")
        except Exception as e:
            print(f"Error saving data: {str(e)}")

    def plot_spectrum(self, frequencies, powers):
        """Plot the RF spectrum"""
        plt.figure(figsize=(12, 6))
        plt.plot(frequencies, powers)
        plt.xlabel('Frequency (MHz)')
        plt.ylabel('Power (dB)')
        plt.title(f'RF Spectrum - Center: {self.center_freq/1e6:.2f} MHz')
        plt.grid(True)
        plt.tight_layout()
        plt.savefig('spectrum.png')
        plt.close()

def main():
    try:
        # Initialize RF monitor
        print("Initializing RF Monitor...")
        rf_monitor = RFMonitor()
        
        print("\nCapturing RF data...")
        samples = rf_monitor.capture_samples()
        
        if samples is not None:
            print(f"Captured {len(samples)} complex samples")
            print("Analyzing spectrum...")
            spectrum_data = rf_monitor.analyze_spectrum(samples)
            
            if spectrum_data:
                # Save the data
                rf_monitor.save_data(spectrum_data)
                
                # Plot the spectrum
                print("Plotting spectrum...")
                rf_monitor.plot_spectrum(
                    spectrum_data['frequencies'],
                    spectrum_data['power_db']
                )
                
                # Print cellular information if found
                if 'cellular_data' in spectrum_data:
                    print("\nCellular Signal Detected:")
                    print(json.dumps(spectrum_data['cellular_data'], indent=2))
            else:
                print("Failed to analyze spectrum data")
        else:
            print("No samples were collected")
        
    except KeyboardInterrupt:
        print("\nMonitoring stopped by user")
    except Exception as e:
        print(f"Error: {str(e)}")

if __name__ == "__main__":
    main()
