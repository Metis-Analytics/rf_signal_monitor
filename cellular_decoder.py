#!/usr/bin/env python3
"""
Cellular Protocol Decoder for IMEI Extraction
This module implements cellular protocol decoding capabilities for extracting
actual IMEIs from cellular devices using a HackRF One.
"""

import numpy as np
from scipy import signal
import subprocess
import os
import time
import logging
import struct
import tempfile
from datetime import datetime

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("cellular_decoder")

class CellularDecoder:
    """
    Advanced cellular protocol decoder for extracting device identifiers
    from cellular signals using a HackRF One.
    """
    
    # GSM/UMTS/LTE message types that may contain IMEI information
    IDENTITY_REQUEST_MSG = 0x18
    IDENTITY_RESPONSE_MSG = 0x19
    
    # Identity types
    IMSI_TYPE = 1
    IMEI_TYPE = 2
    IMEISV_TYPE = 3
    TMSI_TYPE = 4
    
    def __init__(self, sample_rate=20e6, gain=40):
        """
        Initialize the cellular decoder.
        
        Args:
            sample_rate: Sample rate for the HackRF (Hz)
            gain: RF gain setting
        """
        self.sample_rate = sample_rate
        self.gain = gain
        self.temp_dir = tempfile.mkdtemp()
        logger.info(f"Initialized cellular decoder with sample rate {sample_rate/1e6} MHz")
        
        # Verify required tools are available
        self._verify_dependencies()
    
    def _verify_dependencies(self):
        """Verify that required dependencies are installed."""
        try:
            # Check for gr-gsm if we're going to decode GSM
            result = subprocess.run(['which', 'grgsm_decode'], capture_output=True, text=True)
            if result.returncode != 0:
                logger.warning("gr-gsm tools not found. GSM decoding will be limited.")
            
            # Check for LTE Cell Scanner
            result = subprocess.run(['which', 'LTE-Cell-Scanner'], capture_output=True, text=True)
            if result.returncode != 0:
                logger.warning("LTE-Cell-Scanner not found. LTE decoding will be limited.")
                
            logger.info("Dependency check completed")
        except Exception as e:
            logger.error(f"Error checking dependencies: {e}")
    
    def capture_and_decode(self, center_freq, duration=5, technology='auto'):
        """
        Capture and decode cellular signals to extract device identifiers.
        
        Args:
            center_freq: Center frequency in Hz
            duration: Capture duration in seconds
            technology: Cellular technology to decode ('gsm', 'umts', 'lte', or 'auto')
            
        Returns:
            List of extracted device identifiers
        """
        logger.info(f"Capturing {technology} signals at {center_freq/1e6} MHz for {duration}s")
        
        # Determine which decoder to use based on frequency and technology
        if technology == 'auto':
            if 850e6 <= center_freq <= 900e6 or 1800e6 <= center_freq <= 1900e6:
                technology = 'gsm'
            elif 700e6 <= center_freq <= 800e6 or 2500e6 <= center_freq <= 2700e6:
                technology = 'lte'
            elif 1900e6 <= center_freq <= 2200e6:
                technology = 'umts'
            else:
                technology = 'lte'  # Default to LTE for unknown bands
        
        # Capture samples using HackRF
        samples = self._capture_samples(center_freq, duration)
        if samples is None:
            return []
        
        # Decode based on technology
        if technology == 'gsm':
            return self._decode_gsm(samples, center_freq)
        elif technology == 'umts':
            return self._decode_umts(samples, center_freq)
        elif technology == 'lte':
            return self._decode_lte(samples, center_freq)
        else:
            logger.error(f"Unknown technology: {technology}")
            return []
    
    def _capture_samples(self, center_freq, duration):
        """
        Capture RF samples using HackRF.
        
        Args:
            center_freq: Center frequency in Hz
            duration: Capture duration in seconds
            
        Returns:
            Numpy array of complex samples
        """
        try:
            # Create temporary file for samples
            samples_file = os.path.join(self.temp_dir, 'samples.bin')
            
            # Construct hackrf_transfer command with higher sample rate for better decoding
            cmd = [
                'hackrf_transfer',
                '-r', samples_file,
                '-f', str(int(center_freq)),
                '-s', str(int(self.sample_rate)),
                '-n', str(int(self.sample_rate * duration)),  # Number of samples
                '-l', str(self.gain),  # LNA gain
                '-g', str(self.gain),  # VGA gain
                '-a', '1'    # Amp enable
            ]
            
            # Run the command
            logger.info(f"Running: {' '.join(cmd)}")
            result = subprocess.run(cmd, capture_output=True, text=True)
            
            if result.returncode != 0:
                logger.error(f"hackrf_transfer failed: {result.stderr}")
                return None
            
            # Check if file exists and has content
            if not os.path.exists(samples_file):
                logger.error("Samples file was not created")
                return None
            
            if os.path.getsize(samples_file) == 0:
                logger.error("Samples file is empty")
                return None
            
            # Read the binary data
            with open(samples_file, 'rb') as f:
                data = f.read()
            
            # Convert to numpy array
            samples = np.frombuffer(data, dtype=np.int8)
            
            # Convert to complex numbers (I/Q data)
            samples = samples[::2] + 1j * samples[1::2]
            samples = samples.astype(np.complex64)
            
            # Clean up
            os.remove(samples_file)
            
            return samples
            
        except Exception as e:
            logger.error(f"Error capturing samples: {e}")
            if os.path.exists(samples_file):
                os.remove(samples_file)
            return None
    
    def _decode_gsm(self, samples, center_freq):
        """
        Decode GSM signals to extract IMEIs.
        
        Args:
            samples: Complex samples
            center_freq: Center frequency in Hz
            
        Returns:
            List of extracted IMEIs
        """
        logger.info("Decoding GSM signals")
        imeis = []
        
        try:
            # Save samples to temporary file for gr-gsm processing
            temp_file = os.path.join(self.temp_dir, 'gsm_samples.cfile')
            samples.tofile(temp_file)
            
            # Use gr-gsm to decode GSM bursts
            # This is a simplified example - actual implementation would use gr-gsm Python API
            cmd = [
                'grgsm_decode',
                '-c', temp_file,
                '-f', str(int(center_freq)),
                '-s', str(int(self.sample_rate)),
                '-m', 'BCCH'  # Broadcast Control Channel
            ]
            
            logger.info(f"Running: {' '.join(cmd)}")
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            
            # Parse output for IMEI information
            output = result.stdout
            for line in output.split('\n'):
                if "IDENTITY RESPONSE" in line and "IMEI" in line:
                    # Extract IMEI from response
                    parts = line.split("IMEI:")
                    if len(parts) > 1:
                        imei = parts[1].strip().split()[0]
                        if self._validate_imei(imei):
                            imeis.append(imei)
                            logger.info(f"Found GSM IMEI: {imei}")
            
            # Clean up
            os.remove(temp_file)
            
        except Exception as e:
            logger.error(f"Error decoding GSM: {e}")
            if os.path.exists(temp_file):
                os.remove(temp_file)
        
        return imeis
    
    def _decode_umts(self, samples, center_freq):
        """
        Decode UMTS signals to extract IMEIs.
        
        Args:
            samples: Complex samples
            center_freq: Center frequency in Hz
            
        Returns:
            List of extracted IMEIs
        """
        logger.info("Decoding UMTS signals")
        imeis = []
        
        try:
            # UMTS decoding is more complex and would require specialized libraries
            # This is a placeholder for actual UMTS decoding implementation
            # In a real implementation, you would use libraries like:
            # - OpenBTS-UMTS
            # - srsRAN (formerly srsLTE)
            
            # For demonstration, we'll simulate finding IMEIs
            # In a real implementation, this would be replaced with actual decoding
            logger.info("UMTS decoding requires specialized libraries")
            
            # Advanced signal processing would be implemented here
            # For now, we'll return an empty list
            
        except Exception as e:
            logger.error(f"Error decoding UMTS: {e}")
        
        return imeis
    
    def _decode_lte(self, samples, center_freq):
        """
        Decode LTE signals to extract IMEIs.
        
        Args:
            samples: Complex samples
            center_freq: Center frequency in Hz
            
        Returns:
            List of extracted IMEIs
        """
        logger.info("Decoding LTE signals")
        imeis = []
        
        try:
            # Save samples to temporary file for LTE-Cell-Scanner
            temp_file = os.path.join(self.temp_dir, 'lte_samples.bin')
            samples.tofile(temp_file)
            
            # Use LTE-Cell-Scanner to identify cells
            # This is a simplified example - actual implementation would be more complex
            cmd = [
                'LTE-Cell-Scanner',
                '-i', temp_file,
                '-s', str(int(self.sample_rate)),
                '-f', str(int(center_freq/1e6))  # MHz
            ]
            
            logger.info(f"Running: {' '.join(cmd)}")
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
            
            # In a real implementation, you would:
            # 1. Identify active cells
            # 2. Decode PDSCH (Physical Downlink Shared Channel)
            # 3. Extract RRC (Radio Resource Control) messages
            # 4. Look for Identity Request/Response messages containing IMEIs
            
            # For demonstration, we'll log that this requires specialized processing
            logger.info("LTE IMEI extraction requires specialized signal processing")
            
            # Clean up
            os.remove(temp_file)
            
        except Exception as e:
            logger.error(f"Error decoding LTE: {e}")
            if os.path.exists(temp_file):
                os.remove(temp_file)
        
        return imeis
    
    def _validate_imei(self, imei):
        """
        Validate an IMEI using the Luhn algorithm.
        
        Args:
            imei: IMEI string to validate
            
        Returns:
            True if valid, False otherwise
        """
        if not imei or not imei.isdigit() or len(imei) != 15:
            return False
        
        # Apply Luhn algorithm
        total = 0
        for i, digit in enumerate(imei[:-1]):
            d = int(digit)
            if i % 2 == 1:  # Odd position (0-indexed)
                d *= 2
                if d > 9:
                    d -= 9
            total += d
        
        check_digit = (10 - (total % 10)) % 10
        return check_digit == int(imei[-1])
    
    def cleanup(self):
        """Clean up temporary files."""
        try:
            if os.path.exists(self.temp_dir):
                for file in os.listdir(self.temp_dir):
                    os.remove(os.path.join(self.temp_dir, file))
                os.rmdir(self.temp_dir)
                logger.info("Cleaned up temporary files")
        except Exception as e:
            logger.error(f"Error cleaning up: {e}")


# Example usage
if __name__ == "__main__":
    decoder = CellularDecoder()
    
    # Example: Decode GSM signals at 900 MHz
    imeis = decoder.capture_and_decode(900e6, duration=10, technology='gsm')
    print(f"Found {len(imeis)} IMEIs: {imeis}")
    
    # Clean up
    decoder.cleanup()
