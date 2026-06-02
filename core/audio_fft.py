import os
import sys
import time
import ctypes
import logging
import threading
import subprocess
import numpy as np
import pyaudio
from typing import Optional, Callable, List

# Setup logger
logger = logging.getLogger("AudioFFT")

# Context manager to temporarily redirect C-level stderr to /dev/null to silence ALSA logs
from contextlib import contextmanager

@contextmanager
def silence_stderr():
    """Context manager to temporarily redirect C-level stderr to /dev/null."""
    try:
        stderr_fd = sys.stderr.fileno()
    except Exception:
        stderr_fd = None

    if stderr_fd is not None:
        old_stderr = os.dup(stderr_fd)
        try:
            devnull = os.open(os.devnull, os.O_WRONLY)
            os.dup2(devnull, stderr_fd)
            os.close(devnull)
            yield
        finally:
            os.dup2(old_stderr, stderr_fd)
            os.close(old_stderr)
    else:
        yield


def get_default_monitor_source() -> Optional[str]:
    """
    Attempts to retrieve the default PulseAudio/PipeWire monitor source name.
    1. Tries pactl get-default-sink + '.monitor'
    2. Falls back to parsing pactl list sources short for any source containing '.monitor'
    """
    # Attempt 1: get default sink and append .monitor
    try:
        sink = subprocess.check_output(["pactl", "get-default-sink"], stderr=subprocess.DEVNULL).decode().strip()
        if sink:
            return sink + ".monitor"
    except Exception:
        pass
    
    # Attempt 2: parse pactl list sources short and find a monitor
    try:
        sources_raw = subprocess.check_output(["pactl", "list", "sources", "short"], stderr=subprocess.DEVNULL).decode()
        for line in sources_raw.splitlines():
            parts = line.split()
            if len(parts) >= 2:
                name = parts[1]
                if ".monitor" in name:
                    return name
    except Exception:
        pass
        
    return None


class AudioFFTProcessor(threading.Thread):
    """
    Captures system audio output loopback, computes real-time FFT,
    groups frequency bands logarithmically, and features an intelligent sleep mode when silent.
    """
    def __init__(
        self,
        num_bins: int = 64,
        fps: int = 30,
        rms_threshold: float = 15.0,
        smooth_factor: float = 0.2,
        callback: Optional[Callable[[List[float]], None]] = None
    ):
        super().__init__()
        self.num_bins = num_bins
        self.fps = fps
        self.target_interval = 1.0 / fps
        self.rms_threshold = rms_threshold
        self.smooth_factor = smooth_factor
        self.callback = callback
        
        self.running = False
        self.pyaudio_instance = None
        self.stream = None
        self.prev_bins = None
        
        # Audio configuration constants
        self.sample_rate = 44100
        self.chunk_size = 2048
        self.channels = 2
        
        # Precomputed frequency bin parameters
        self.bin_edges = None
        self.bin_to_freq_indices = None
        self.bin_centers = None
        
        self.daemon = True  # Allows thread to exit when main application exits

    def _precompute_bins(self):
        """Precomputes frequency grouping matrices to minimize CPU time in the real-time loop."""
        min_freq = 30.0
        max_freq = min(5500.0, self.sample_rate / 2.0)
        
        # Generate log-spaced boundaries for output bins
        self.bin_edges = np.logspace(np.log10(min_freq), np.log10(max_freq), self.num_bins + 1)
        self.bin_centers = [(self.bin_edges[i] + self.bin_edges[i+1]) / 2.0 for i in range(self.num_bins)]
        
        # Determine the FFT bin frequencies
        freqs = np.fft.rfftfreq(self.chunk_size, 1.0 / self.sample_rate)
        
        # Map each linear FFT frequency bin to one of the output bins
        bin_indices = np.digitize(freqs, self.bin_edges) - 1
        
        # Store index lists for quick extraction in loop
        self.bin_to_freq_indices = [np.where(bin_indices == i)[0] for i in range(self.num_bins)]

    def _init_stream(self) -> bool:
        """Initializes the PyAudio instance and opens the loopback input stream."""
        self._cleanup_stream()
        
        # Discover and apply the loopback source in environmental variables
        monitor_source = get_default_monitor_source()
        
        # Use thread lock or just set/restore globally
        old_source = os.environ.get("PULSE_SOURCE")
        if monitor_source:
            logger.info(f"Connecting to loopback monitor source: {monitor_source}")
            os.environ["PULSE_SOURCE"] = monitor_source
        else:
            logger.warning("No loopback monitor source found. Falling back to default system input.")
            
        try:
            with silence_stderr():
                self.pyaudio_instance = pyaudio.PyAudio()
                
                # Attempt to open as stereo 44.1kHz
                self.sample_rate = 44100
                self.channels = 2
                self.stream = self.pyaudio_instance.open(
                    format=pyaudio.paInt16,
                    channels=self.channels,
                    rate=self.sample_rate,
                    input=True,
                    frames_per_buffer=self.chunk_size
                )
        except Exception as e:
            logger.warning(f"Failed to open stereo 44.1kHz stream: {e}. Trying mono 16kHz fallback...")
            try:
                with silence_stderr():
                    self.sample_rate = 16000
                    self.channels = 1
                    self.stream = self.pyaudio_instance.open(
                        format=pyaudio.paInt16,
                        channels=self.channels,
                        rate=self.sample_rate,
                        input=True,
                        frames_per_buffer=self.chunk_size
                    )
            except Exception as ex:
                logger.critical(f"Failed to open fallback audio stream: {ex}")
                raise ex
        finally:
            # Restore original PULSE_SOURCE to prevent side-effects in other components/threads
            if old_source is not None:
                os.environ["PULSE_SOURCE"] = old_source
            elif "PULSE_SOURCE" in os.environ:
                del os.environ["PULSE_SOURCE"]
                
        # Re-precompute frequency grouping using actual sample rate
        self._precompute_bins()
        return True

    def _cleanup_stream(self):
        """Safely closes PyAudio stream and terminates instance."""
        if self.stream:
            try:
                self.stream.stop_stream()
                self.stream.close()
            except Exception:
                pass
            self.stream = None
            
        if self.pyaudio_instance:
            try:
                self.pyaudio_instance.terminate()
            except Exception:
                pass
            self.pyaudio_instance = None

    def stop(self):
        """Stops the processor loop."""
        self.running = False

    def run(self):
        """Main execution thread loop."""
        self.running = True
        logger.info("Starting Audio FFT capture thread...")
        
        while self.running:
            try:
                self._init_stream()
                self._main_loop()
            except Exception as e:
                logger.error(f"Error in Audio FFT loop: {e}. Retrying in 2.0s...")
                self._cleanup_stream()
                if self.running:
                    time.sleep(2.0)
            finally:
                self._cleanup_stream()
                
        logger.info("Audio FFT capture thread stopped.")

    def _main_loop(self):
        """Internal real-time capture and processing loop."""
        consecutive_silent_frames = 0
        in_sleep_mode = False
        
        # Window function to minimize spectral leakage
        window = np.hanning(self.chunk_size)
        freqs = np.fft.rfftfreq(self.chunk_size, 1.0 / self.sample_rate)
        
        while self.running:
            start_time = time.time()
            
            if in_sleep_mode:
                # Sleep mode: low CPU poll every 0.1s
                time.sleep(0.1)
                
                # Check if stream is still active, read a chunk to verify RMS
                if not self.stream:
                    break
                    
                try:
                    # Clear buffer build-up to inspect current audio state
                    avail = self.stream.get_read_available()
                    if avail > self.chunk_size:
                        self.stream.read(avail - self.chunk_size, exception_on_overflow=False)
                    
                    raw_data = self.stream.read(self.chunk_size, exception_on_overflow=False)
                except Exception as e:
                    logger.warning(f"Error reading stream in sleep mode: {e}")
                    raise e
                    
                if not raw_data:
                    continue
                    
                # Convert to numpy
                audio_data = np.frombuffer(raw_data, dtype=np.int16).astype(np.float32)
                if self.channels == 2:
                    audio_data = audio_data.reshape(-1, 2).mean(axis=1)
                    
                rms = np.sqrt(np.mean(np.square(audio_data)))
                
                if rms >= self.rms_threshold:
                    logger.info(f"System audio detected (RMS: {rms:.2f}). Waking up FFT processor.")
                    in_sleep_mode = False
                    consecutive_silent_frames = 0
                    # Flush stream buffer to start fresh and avoid lag
                    try:
                        avail = self.stream.get_read_available()
                        if avail > 0:
                            self.stream.read(avail, exception_on_overflow=False)
                    except Exception:
                        pass
                continue
                
            else:
                # Active mode: process FFT at 30 FPS
                if not self.stream:
                    break
                    
                try:
                    raw_data = self.stream.read(self.chunk_size, exception_on_overflow=False)
                except Exception as e:
                    logger.warning(f"Error reading stream in active mode: {e}")
                    raise e
                    
                if not raw_data:
                    continue
                    
                audio_data = np.frombuffer(raw_data, dtype=np.int16).astype(np.float32)
                if self.channels == 2:
                    audio_data = audio_data.reshape(-1, 2).mean(axis=1)
                    
                # Calculate RMS
                rms = np.sqrt(np.mean(np.square(audio_data)))
                
                if rms < self.rms_threshold:
                    consecutive_silent_frames += 1
                    # If silent for more than 1 second (~30 frames)
                    if consecutive_silent_frames > 30:
                        logger.info("System audio silent. Putting FFT processor to sleep...")
                        in_sleep_mode = True
                        self.prev_bins = None
                        if self.callback:
                            # Emit zeroed bins once to clear any visualizer
                            self.callback([0.0] * self.num_bins)
                        continue
                else:
                    consecutive_silent_frames = 0
                
                # Apply window function on normalized audio data (values in [-1.0, 1.0])
                normalized_data = audio_data / 32768.0
                windowed_data = normalized_data * window
                
                # Perform FFT
                fft_res = np.fft.rfft(windowed_data)
                mags = np.abs(fft_res) / self.chunk_size
                mags[0] = 0.0  # Zero out DC component to prevent constant first bar bias
                
                # Group frequencies into bins
                bin_values = np.zeros(self.num_bins)
                for i in range(self.num_bins):
                    indices = self.bin_to_freq_indices[i]
                    if len(indices) > 0:
                        bin_values[i] = np.mean(mags[indices])
                    else:
                        # Fallback to interpolation for empty bins (low-frequencies)
                        bin_values[i] = np.interp(self.bin_centers[i], freqs, mags)
                        
                # Apply smoothing
                if self.prev_bins is None:
                    self.prev_bins = bin_values
                else:
                    bin_values = self.smooth_factor * bin_values + (1.0 - self.smooth_factor) * self.prev_bins
                    self.prev_bins = bin_values
                    
                # Execute callback
                if self.callback:
                    try:
                        self.callback(bin_values.tolist())
                    except Exception as e:
                        logger.error(f"Error executing FFT callback: {e}")
                        
                # Throttle to target FPS
                elapsed = time.time() - start_time
                sleep_time = self.target_interval - elapsed
                if sleep_time > 0:
                    time.sleep(sleep_time)
