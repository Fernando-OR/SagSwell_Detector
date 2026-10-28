import numpy as np
from scipy.integrate import odeint
import matplotlib.pyplot as plt

# ============================================
# PARAMETERS
# ============================================
# System (60 Hz base)
f = 60.0  # Hz
omega = 2 * np.pi * f  # rad/s
Vbase = 1.0  # per-unit (1 pu = nominal voltage)
Sbase = 100e6  # VA

# Source (Generator Thevenin equivalent)
Xs = 0.2  # source reactance (pu) — controls stiffness
Rs = 0.01  # source resistance (pu)
Vs = 1.0  # source voltage (pu, before fault)

# Transmission Line
R_line = 0.05  # resistance (pu)
L_line = 0.15  # inductance (pu) → X = ωL
X_line = omega * L_line / (omega * 0.1)  # normalized reactance

# Load
P_load = 0.5  # MW (pu)
Q_load = 0.2  # MVAr (pu)

# Fault
fault_time = 0.5  # seconds (fault starts here)
fault_duration = 5 / f  # 5 cycles
Zf = 0.01  # fault impedance (pu)

# ============================================
# SYSTEM MODEL: dI/dt = (V - Z*I) / L
# ============================================
def system_ode(state, t):
    """
    State vector: [I_real, I_imag]  (complex current as two reals)
    Returns: dI/dt
    """
    I_real, I_imag = state
    I = I_real + 1j * I_imag
    
    # --- Determine operating point ---
    if fault_time <= t <= fault_time + fault_duration:
        # FAULT: short circuit at load bus through Zf
        Z_total = Rs + 1j * Xs + R_line + 1j * X_line + Zf
        Vpcc = 0.0 + 1j * 0.0  # voltage at fault point ≈ 0
    else:
        # NORMAL: load draws P+jQ
        Z_total = Rs + 1j * Xs + R_line + 1j * X_line
        Vpcc = Vs  # voltage at load (simplified, ignoring load voltage drop)
    
    # Kirchhoff's voltage law: Vs = I*Z_total + Vpcc
    # → dI/dt = (Vs - I*Z_total) / L
    L_eq = X_line / omega  # equivalent inductance
    dI_dt = (Vs - I * Z_total) / L_eq
    
    return [dI_dt.real, dI_dt.imag]

# ============================================
# SIMULATION
# ============================================
t = np.linspace(0, 2.0, 10000)  # 2 seconds
initial_state = [P_load, Q_load]  # initial current (pu)

solution = odeint(system_ode, initial_state, t)
I_real = solution[:, 0]
I_imag = solution[:, 1]
I_complex = I_real + 1j * I_imag

# --- Voltage at load bus ---
# V_load = Vs - I*(Rs + jXs + R_line + jX_line)
Z_equiv = Rs + 1j * Xs + R_line + 1j * X_line
V_load = Vs - I_complex * Z_equiv

# --- RMS voltage (1-cycle window average) ---
samples_per_cycle = len(t) / (t[-1] * f)
window = int(samples_per_cycle)

V_rms = np.zeros(len(t))
for i in range(window, len(t)):
    V_rms[i] = np.sqrt(np.mean(np.abs(V_load[i-window:i])**2))

# ============================================
# PLOTTING
# ============================================
fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 8))

# Voltage waveform
ax1.plot(t, np.abs(V_load), label='|V(t)| instantaneous', alpha=0.6)
ax1.plot(t, V_rms, label='V_RMS (1-cycle window)', linewidth=2, color='red')
ax1.axvline(fault_time, color='gray', linestyle='--', label='Fault start')
ax1.axvline(fault_time + fault_duration, color='gray', linestyle='--', label='Fault clear')
ax1.set_ylabel('Voltage (pu)')
ax1.set_xlabel('Time (s)')
ax1.legend()
ax1.grid()
ax1.set_ylim([0, 1.2])

# Voltage sag depth (% of nominal)
sag_depth = (1.0 - V_rms) * 100  # percentage
ax2.plot(t, sag_depth, linewidth=2, color='red')
ax2.fill_between(t, 0, sag_depth, alpha=0.3)
ax2.axhline(10, color='orange', linestyle='--', label='ANSI C84.1 Range A threshold')
ax2.set_ylabel('Sag Depth (%)')
ax2.set_xlabel('Time (s)')
ax2.legend()
ax2.grid()

plt.tight_layout()
plt.show()

# ============================================
# ANALYSIS: Extract sag metrics
# ============================================
sag_fault_window = (t >= fault_time) & (t <= fault_time + fault_duration)
V_min = np.min(V_rms[sag_fault_window])
sag_magnitude = (1.0 - V_min) * 100  # % sag

print(f"Sag Depth: {sag_magnitude:.1f}%")
print(f"Sag Duration: {fault_duration*1000:.1f} ms ({fault_duration*f:.1f} cycles)")
print(f"Recovery Time: ~{2*(fault_duration):.3f} s")  # rough estimate
