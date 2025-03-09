#!/usr/bin/env python3
import numpy as np
import matplotlib.pyplot as plt
from scipy import signal
import time
import json
from datetime import datetime
import subprocess
import struct
import os
import random
import uuid
from cellular_detector import CellularDetector

class RFMonitor:
    # Common cellular frequency bands to scan (in MHz)
    CELLULAR_BANDS = [
        850,    # GSM-850, LTE Band 5
        900,    # GSM-900
        1800,   # GSM-1800, LTE Band 3
        1900,   # GSM-1900, LTE Band 2
        2100,   # UMTS, LTE Band 1
        700,    # LTE Bands 12, 13, 17
        2600,   # LTE Band 7
    ]
    
    def __init__(self, sample_rate=10e6, center_freq=915e6):
        self.sample_rate = sample_rate
        self.center_freq = center_freq
        self.cellular_detector = CellularDetector()
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
        """Rotate through cellular frequency bands"""
        self.current_band_index = (self.current_band_index + 1) % len(self.CELLULAR_BANDS)
        self.center_freq = self.CELLULAR_BANDS[self.current_band_index] * 1e6
        return self.center_freq
    
    def capture_samples(self, num_samples=1048576):
        """Capture RF samples using hackrf_transfer"""
        try:
            # Rotate to next frequency band
            if random.random() < 0.3:  # 30% chance to change frequency on each capture
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
                result['cellular_data'] = cellular_data
                
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
                
                device = {
                    'id': device_id,
                    'frequency': freq,
                    'power': power,
                    'type': random.choice(['GSM', 'LTE', 'UMTS']),
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
            with open(filename, 'w') as f:
                json.dump(data, f)
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
