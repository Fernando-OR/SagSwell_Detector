import numpy as np
import matplotlib.pyplot as plt

class VoltageGenerator:
    """Simulates AC generator voltage with sporadic sags and swells."""
    
    def __init__(self, nominal_voltage=230, frequency=50, sample_rate=10000):
        """
        Parameters:
        - nominal_voltage: RMS voltage in volts (default 230V for EU standard)
        - frequency: AC frequency in Hz (50 or 60)
        - sample_rate: samples per second
        """
        self.V_nom = nominal_voltage
        self.freq = frequency
        self.fs = sample_rate
        self.dt = 1 / sample_rate
        self.peak_voltage = nominal_voltage * np.sqrt(2)  # Convert RMS to peak
        self.t = 0
        
    def generate_voltage(self, duration=5, sag_events=3, swell_events=2):
        """
        Generate voltage waveform with random sag/swell events.
        
        Parameters:
        - duration: simulation time in seconds
        - sag_events: number of voltage sags to introduce
        - swell_events: number of voltage swells to introduce
        
        Returns: time array, voltage array, event markers (dict)
        """
        n_samples = int(duration * self.fs)
        time = np.arange(n_samples) * self.dt
        voltage = np.zeros(n_samples)
        
        # Generate clean sinusoidal voltage
        voltage = self.peak_voltage * np.sin(2 * np.pi * self.freq * time)
        
        # Storage for event information
        events = {'sags': [], 'swells': []}
        
        # Introduce random sag events
        for _ in range(sag_events):
            start_idx = np.random.randint(0, n_samples - int(0.5 * self.fs))
            duration_samples = np.random.randint(int(0.1 * self.fs), int(0.5 * self.fs))
            depth = np.random.uniform(0.2, 0.7)  # Sag to 20-70% of nominal
            
            end_idx = min(start_idx + duration_samples, n_samples)
            sag_factor = 1 - depth
            
            # Apply sag by reducing amplitude
            voltage[start_idx:end_idx] *= sag_factor
            
            events['sags'].append({
                'start_time': time[start_idx],
                'end_time': time[end_idx - 1],
                'depth': depth,
                'residual_voltage': sag_factor * self.V_nom
            })
        
        # Introduce random swell events
        for _ in range(swell_events):
            start_idx = np.random.randint(0, n_samples - int(0.5 * self.fs))
            duration_samples = np.random.randint(int(0.1 * self.fs), int(0.5 * self.fs))
            magnitude = np.random.uniform(1.1, 1.3)  # Swell to 110-130% of nominal
            
            end_idx = min(start_idx + duration_samples, n_samples)
            
            # Apply swell by increasing amplitude
            voltage[start_idx:end_idx] *= magnitude
            
            events['swells'].append({
                'start_time': time[start_idx],
                'end_time': time[end_idx - 1],
                'magnitude': magnitude,
                'peak_voltage': magnitude * self.V_nom
            })
        
        return time, voltage, events
    
    def calculate_rms(self, voltage_samples, window_size=None):
        """Calculate RMS voltage over a sliding window."""
        if window_size is None:
            window_size = self.fs  # Default 1-second window
        
        rms_values = []
        for i in range(0, len(voltage_samples) - window_size):
            rms = np.sqrt(np.mean(voltage_samples[i:i+window_size]**2))
            rms_values.append(rms)
        
        return np.array(rms_values)


# ============ EXAMPLE USAGE ============
if __name__ == "__main__":
    # Create generator
    gen = VoltageGenerator(nominal_voltage=230, frequency=50, sample_rate=10000)
    
    # Generate 5-second waveform with 3 sags and 2 swells
    time, voltage, events = gen.generate_voltage(duration=5, sag_events=3, swell_events=2)
    
    # Calculate RMS voltage
    rms_voltage = gen.calculate_rms(voltage, window_size=500)
    rms_time = np.arange(len(rms_voltage)) / gen.fs
    
    # Print event information
    print("=== VOLTAGE SAG/SWELL EVENTS ===\n")
    for i, sag in enumerate(events['sags'], 1):
        print(f"Sag {i}:")
        print(f"  Time: {sag['start_time']:.3f}s - {sag['end_time']:.3f}s")
        print(f"  Depth: {sag['depth']*100:.1f}%")
        print(f"  Residual voltage: {sag['residual_voltage']:.1f}V\n")
    
    for i, swell in enumerate(events['swells'], 1):
        print(f"Swell {i}:")
        print(f"  Time: {swell['start_time']:.3f}s - {swell['end_time']:.3f}s")
        print(f"  Magnitude: {(swell['magnitude']-1)*100:.1f}% increase")
        print(f"  Peak voltage: {swell['peak_voltage']:.1f}V\n")
    
    # Plot results
    fig, axes = plt.subplots(2, 1, figsize=(12, 8))
    
    # Plot instantaneous voltage
    axes[0].plot(time, voltage, 'b-', linewidth=0.8, label='Instantaneous Voltage')
    axes[0].axhline(gen.peak_voltage, color='g', linestyle='--', alpha=0.5, label=f'Nominal Peak ({gen.peak_voltage:.1f}V)')
    axes[0].axhline(-gen.peak_voltage, color='g', linestyle='--', alpha=0.5)
    axes[0].set_ylabel('Voltage (V)', fontsize=11)
    axes[0].set_title('Generator Voltage with Sags and Swells', fontsize=12, fontweight='bold')
    axes[0].grid(True, alpha=0.3)
    axes[0].legend()
    
    # Plot RMS voltage
    axes[1].plot(rms_time, rms_voltage, 'r-', linewidth=1.5, label='RMS Voltage')
    axes[1].axhline(gen.V_nom, color='g', linestyle='--', alpha=0.7, label=f'Nominal RMS ({gen.V_nom}V)')
    axes[1].axhline(gen.V_nom * 0.9, color='orange', linestyle=':', alpha=0.7, label='Sag Threshold (90%)')
    axes[1].axhline(gen.V_nom * 1.1, color='purple', linestyle=':', alpha=0.7, label='Swell Threshold (110%)')
    axes[1].set_xlabel('Time (s)', fontsize=11)
    axes[1].set_ylabel('RMS Voltage (V)', fontsize=11)
    axes[1].set_title('RMS Voltage Over Time', fontsize=12, fontweight='bold')
    axes[1].grid(True, alpha=0.3)
    axes[1].legend()
    
    plt.tight_layout()
    plt.show()
