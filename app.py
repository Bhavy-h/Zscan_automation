import streamlit as st
import matplotlib.pyplot as plt
import io
import zipfile
import numpy as np
from scipy.optimize import minimize

# --- Theoretical Sheik-Bahae Equations ---

def oa_sheik_bahae(z, q00, z_shift, z0):
    """Equation 6 summation for Open Aperture"""
    if z0 == 0: z0 = 1e-10 # Prevent division by zero during scipy minimization
    q0_z = q00 / (1 + ((z - z_shift) / z0)**2)
    T = np.zeros_like(z)
    for m in range(16): # Sum from m=0 to 15
        term = ((-q0_z)**m) / ((m + 1)**1.5)
        T += term
    return T

def ca_sheik_bahae(z, dPhi0, z_shift, baseline, z0_calc):
    """Standard CA equation for small phase shift"""
    if z0_calc == 0: z0_calc = 1e-10
    x = (z - z_shift) / z0_calc
    return baseline + (4 * dPhi0 * x) / (((x**2) + 9) * ((x**2) + 1))

# --- Main Processing Function ---

def process_and_plot(file_content, file_name, params, mode):
    # Fallback decoding for older lab equipment files
    try:
        lines = file_content.decode('utf-8').splitlines()
    except UnicodeDecodeError:
        lines = file_content.decode('latin-1').splitlines()
        
    distances = []
    voltages = []
    
    # 1. Parse Data
    if any("***End_of_Header***" in line for line in lines):
        header_count = 0
        data_start_idx = 0
        for i, line in enumerate(lines):
            if "***End_of_Header***" in line:
                header_count += 1
                if header_count == 2:
                    data_start_idx = i + 2 
                    break
        x_data_line = lines[data_start_idx].strip().split('\t')
        y_data_line = lines[data_start_idx + 1].strip().split('\t')
        distances = [float(val) for val in x_data_line if val.strip()]
        voltages = [float(val) for val in y_data_line if val.strip()]
    else:
        for line in lines:
            if line.strip(): 
                # Robustly handle commas, tabs, and spaces
                clean_line = line.replace(',', ' ').replace('\t', ' ')
                parts = clean_line.split()
                if len(parts) >= 2:
                    try:
                        distances.append(float(parts[0].strip()))
                        voltages.append(float(parts[1].strip()))
                    except ValueError:
                        continue

    # Catch empty arrays before they crash the math functions
    if len(distances) == 0:
        raise ValueError("Could not extract any numerical data. Please verify the file formatting.")

    raw_z_mm = np.array(distances)
    volt_arr = np.array(voltages)
    
    sort_indices = np.argsort(raw_z_mm)
    raw_z_mm = raw_z_mm[sort_indices]
    volt_arr = volt_arr[sort_indices]

    # 2. Baseline Normalization
    edge_points = max(5, int(len(volt_arr) * 0.1))
    baseline_v = (np.mean(volt_arr[:edge_points]) + np.mean(volt_arr[-edge_points:])) / 2
    data_norm = volt_arr / baseline_v

    # Convert distance to cm for physics equations
    z_cm = raw_z_mm * 0.1 

    # 3. Experimental Constants
    lambda_cm = params['wavelength'] * 1e-7
    energy_j = params['energy'] * 1e-9
    pulse_s = params['pulse'] * 1e-15
    focal_cm = params['focal']
    diam_cm = params['waist'] * 1e-4 
    L_cm = params['thickness'] * 1e-1
    S = params['aperture_S']

    # Derived Optical Parameters
    u0 = 2 * lambda_cm * focal_cm / (np.pi * diam_cm)
    z0_calc = np.pi * (u0**2) / lambda_cm
    I0 = energy_j / (np.pi * (u0**2) * pulse_s)
    Leff = L_cm

    # 4. Curve Fitting
    z_smooth_cm = np.linspace(np.min(z_cm), np.max(z_cm), 1000)
    
    if mode == "Open Aperture (β)":
        idx_min = np.argmin(data_norm)
        z_shift_guess = z_cm[idx_min]
        
        initial_guess = [0.1, z_shift_guess, z0_calc]
        
        def sse_oa(p):
            return np.sum((data_norm - oa_sheik_bahae(z_cm, p[0], p[1], p[2]))**2)
            
        res = minimize(sse_oa, initial_guess, method='Nelder-Mead', options={'maxiter': 2000})
        q00_fit, z_shift_fit, z0_fit = res.x
        
        coeff = q00_fit / (I0 * Leff)
        coeff_name = "β (cm/W)"
        phenomenon = "Saturable / Reverse Absorption"
        
        T_fit = oa_sheik_bahae(z_smooth_cm, q00_fit, z_shift_fit, z0_fit)
        
    else: 
        idx_max = np.argmax(data_norm)
        idx_min = np.argmin(data_norm)
        z_shift_guess = (z_cm[idx_max] + z_cm[idx_min]) / 2.0
        
        initial_guess = [0.5, z_shift_guess, 1.0]
        
        def sse_ca(p):
            return np.sum((data_norm - ca_sheik_bahae(z_cm, p[0], p[1], p[2], z0_calc))**2)
            
        res = minimize(sse_ca, initial_guess, method='Nelder-Mead', options={'maxiter': 2000})
        dPhi0_fit, z_shift_fit, baseline_fit = res.x
        
        T_fit = ca_sheik_bahae(z_smooth_cm, dPhi0_fit, z_shift_fit, baseline_fit, z0_calc)
        
        T_peak = np.max(T_fit)
        T_valley = np.min(T_fit)
        delta_T_pv = T_peak - T_valley
        
        k = (2 * np.pi) / lambda_cm
        coeff = delta_T_pv / (0.406 * (1 - S)**0.25 * k * I0 * Leff)
        
        if z_smooth_cm[np.argmin(T_fit)] < z_smooth_cm[np.argmax(T_fit)]:
            sign_n2 = 1
            phenomenon = "Self-Focusing (+n₂)"
        else:
            sign_n2 = -1
            phenomenon = "Self-Defocusing (-n₂)"
            
        coeff = coeff * sign_n2
        coeff_name = "n₂ (cm²/W)"

    # 5. Plotting
    fig, ax = plt.subplots(figsize=(10, 6), facecolor='white')
    
    ax.plot(z_cm * 10, data_norm, 'o', markersize=8, markeredgecolor='#801A1A', markerfacecolor='none', markeredgewidth=1.5, label='Experimental Data')
    ax.plot(z_smooth_cm * 10, T_fit, '-', color='#000066', linewidth=2.5, label='Sheik-Bahae Fit')
    
    ax.set_title(f'Theoretical Fit: {file_name}', fontweight='bold')
    ax.set_xlabel('z (mm)', fontsize=12, fontweight='bold')
    ax.set_ylabel('Normalized Transmittance', fontsize=12, fontweight='bold')
    
    y_margin = (np.max(data_norm) - np.min(data_norm)) * 0.1
    ax.set_ylim([np.min(data_norm) - y_margin, np.max(data_norm) + y_margin])
    
    ax.tick_params(direction='in', length=6, width=1.2, which='major', top=True, right=True)
    ax.minorticks_on()
    ax.tick_params(direction='in', length=3, width=1, which='minor', top=True, right=True)
    for spine in ax.spines.values():
        spine.set_linewidth(1.2)
        
    ax.legend(frameon=False, fontsize=11)
    fig.tight_layout()
    
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=300)
    buf.seek(0)
    plt.close(fig)
    
    results = {"buffer": buf, "i0": I0, "coeff": coeff, "coeff_name": coeff_name, "phenomenon": phenomenon, "z0_calc": z0_calc}
    if mode == "Open Aperture (β)":
        results["z0_fit"] = z0_fit
    else:
        results["delta_T"] = delta_T_pv
        
    return results


# --- Streamlit Dashboard UI ---
st.set_page_config(page_title="Ultimate Z-Scan Analyzer", layout="wide")

st.title("⚡ Ultimate Z-Scan Analyzer: Theoretical Fitting")
st.markdown("Automated Sheik-Bahae equation fitting for Open and Closed Aperture experiments.")

# --- Sidebar Configuration ---
st.sidebar.header("1. Analysis Mode")
analysis_mode = st.sidebar.radio("Select Experiment Type:", ["Closed Aperture (n2)", "Open Aperture (β)"])

st.sidebar.header("2. Laser & Optical Setup")
params = {
    "wavelength": st.sidebar.number_input("Wavelength λ (nm)", value=800.0, step=1.0),
    "energy": st.sidebar.number_input("Pulse Energy (nJ)", value=2.1, step=0.1, format="%.2f"),
    "pulse": st.sidebar.number_input("Pulse FWHM (fs)", value=150.0, step=1.0),
    "focal": st.sidebar.number_input("Lens Focal Length (cm)", value=20.0, step=0.5),
    "waist": st.sidebar.number_input("Beam Diam. on lens (µm)", value=5000.0, step=10.0), 
    "thickness": st.sidebar.number_input("Sample Thickness (mm)", value=1.0, step=0.1)
}

if analysis_mode == "Closed Aperture (n2)":
    st.sidebar.header("3. Aperture Settings")
    params["aperture_S"] = st.sidebar.number_input("Aperture Transmittance (S)", value=0.3, min_value=0.01, max_value=0.99, step=0.05)
else:
    params["aperture_S"] = 1.0 

# --- Main Uploader ---
uploaded_files = st.file_uploader("Upload LabVIEW (.txt) or CSV data", type=["txt", "csv", "dat"], accept_multiple_files=True)

if uploaded_files:
    zip_buffer = io.BytesIO()
    tabs = st.tabs([file.name for file in uploaded_files])
    
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
        for i, (uploaded_file, tab) in enumerate(zip(uploaded_files, tabs)):
            file_name = uploaded_file.name
            file_content = uploaded_file.read()
            
            try:
                result = process_and_plot(file_content, file_name, params, analysis_mode)
                
                with tab:
                    st.markdown(f"**Observed Phenomenon:** `{result['phenomenon']}`")
                    
                    m1, m2, m3, m4 = st.columns(4)
                    m1.metric("Peak Intensity (I₀)", f"{result['i0']:.2e} W/cm²")
                    m2.metric(result['coeff_name'], f"{result['coeff']:.4e}")
                    
                    if analysis_mode == "Open Aperture (β)":
                        m3.metric("Theoretical z₀", f"{result['z0_calc']:.4f} cm")
                        m4.metric("Fitted Curve Width (z₀)", f"{abs(result['z0_fit']):.4f} cm")
                    else:
                        m3.metric("Theoretical z₀", f"{result['z0_calc']:.4f} cm")
                        m4.metric("ΔT (Peak-to-Valley)", f"{result['delta_T']:.4f}")
                    
                    st.divider()
                    
                    left_col, mid_col, right_col = st.columns([1, 2, 1])
                    with mid_col:
                        st.image(result['buffer'], use_container_width=True)
                        png_filename = f"{file_name.split('.')[0]}_{analysis_mode[:6]}_Fit.png"
                        st.download_button(
                            label=f"⬇️ Download {file_name} Plot",
                            data=result['buffer'],
                            file_name=png_filename,
                            mime="image/png",
                            key=f"download_btn_{i}"
                        )
                
                zip_file.writestr(png_filename, result['buffer'].getvalue())
                
            except Exception as e:
                with tab:
                    st.error(f"Error processing {file_name}: {e}")
            
    zip_buffer.seek(0)
    
    st.markdown("---")
    left, right = st.columns([3, 1])
    with left:
        st.markdown("### 📦 Batch Export")
    with right:
        st.download_button(
            label="Download All Plots (ZIP)",
            data=zip_buffer,
            file_name=f"ZScan_Theoretical_Fits.zip",
            mime="application/zip",
            type="primary",
            use_container_width=True
        )
