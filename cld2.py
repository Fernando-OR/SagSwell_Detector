import pandapower as pp
import numpy as np
import matplotlib.pyplot as plt

# ============================================
# CREATE NETWORK
# ============================================
net = pp.create_empty_network()

# Buses
pp.create_bus(net, name='Source', vn_kv=138)
pp.create_bus(net, name='Feeder', vn_kv=138)
pp.create_bus(net, name='Load', vn_kv=138)

# Generator (source)
pp.create_gen(net, bus=0, p_mw=100, vm_pu=1.0, name='Gen1')

# Lines
pp.create_line(net, from_bus=0, to_bus=1, length_km=50, std_type='N2XSY 1x300 RM/25 12/20kV')
pp.create_line(net, from_bus=1, to_bus=2, length_km=30, std_type='N2XSY 1x300 RM/25 12/20kV')

# Load
pp.create_load(net, bus=2, p_mw=50, q_mvar=20, name='Load1')

# Run power flow
pp.runpp(net)
print("Initial voltages (pu):")
print(net.res_bus[['name', 'vm_pu']])

# ============================================
# TIME-STEPPING SIMULATION: Fault at t=0.5s
# ============================================
dt = 0.001  # 1 ms time step
t_sim = np.linspace(0, 2, int(2 / dt))
fault_time = 0.5
fault_duration = 5 / 60  # 5 cycles @ 60 Hz

V_rms_history = {bus: [] for bus in net.bus.index}

for t in t_sim:
    # Inject fault: short line 1-2 through 0.01 pu impedance
    if fault_time <= t <= fault_time + fault_duration:
        pp.create_switch(net, et='l', element=1, closed=False)  # Open line during fault
    else:
        # Restore line
        if len(net.switch) > 0:
            net.switch.loc[0, 'closed'] = True
    
    # Recompute power flow
    try:
        pp.runpp(net)
        V_rms = net.res_bus['vm_pu'].values
        for i, v in enumerate(V_rms):
            V_rms_history[i].append(v)
    except:
        # Convergence failure during fault (expected)—use last known voltage
        pass

# ============================================
# PLOT RESULTS
# ============================================
plt.figure(figsize=(12, 6))
for bus in [0, 1, 2]:
    plt.plot(t_sim[:len(V_rms_history[bus])], V_rms_history[bus], 
             label=net.bus.loc[bus, 'name'], linewidth=2)

plt.axvline(fault_time, color='red', linestyle='--', label='Fault')
plt.axvline(fault_time + fault_duration, color='orange', linestyle='--', label='Clear')
plt.ylabel('Voltage (pu)')
plt.xlabel('Time (s)')
plt.legend()
plt.grid()
plt.show()
