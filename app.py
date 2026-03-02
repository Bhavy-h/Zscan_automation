import streamlit as st
import matplotlib.pyplot as plt
import io
import zipfile
import numpy as np
from scipy.signal import savgol_filter

def process_and_plot(file_content, file_name, params, mode):
    lines = file_content.decode('utf-8').splitlines()
    distances = []
    voltages = []
    
    # 1. Parse Data (Handles both LabVIEW and CSV)
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
                parts = line.split(',')
                if len(parts) >= 2:
                    try:
                        distances.append(float(parts[0].strip()))
                        voltages.append(float(parts[1].strip()))
                    except ValueError:
                        continue

    raw_z = np.array(distances)
    volt_arr = np.array(voltages)
    
    # Sort just in case
    sort_indices = np.argsort(raw_z)
    raw_z = raw_z[sort_indices]
    volt_arr = volt_arr[sort_indices]

    # 2. Baseline Normalization
    # Uses the outer edges (linear region) to find the un-lensed baseline
    edge_points = max(3, int(len(volt_arr) * 0.05))
    baseline_v = (np.mean(volt_arr[:edge_points]) + np.mean(volt_arr[-edge_points:])) / 2
    normalized_t = volt_arr / baseline_v

    # 3. Smoothing
    window_len = min(int(params['smooth_window']), len(raw_z) - (0 if len(raw_z) % 2 != 0 else 1))
    if window_len < 3: window_len = 3 
    try:
        smoothed_t = savgol_filter(normalized_t, window_length=window_len, polyorder=3)
    except Exception:
        smoothed_t = normalized_t

    # 4. Auto-Centering Z-Axis & Extracting Delta T
    if mode == "Closed Aperture (n2)":
        idx_max = np.argmax(smoothed_t)
        idx_min = np.argmin(smoothed_t)
        # Focus (z=0) is roughly halfway between the peak and the valley
        z_focus = (raw_z[idx_max] + raw_z[idx_min]) / 2.0
        delta_t = smoothed_t[idx_max] - smoothed_t[idx_min]
    else:
        # Open aperture: Focus is directly at the deepest part of the valley
        idx_min = np.argmin(smoothed_t)
        z_focus = raw_z[idx_min]
        # Delta T is the drop from the baseline (1.0) to the valley
        delta_t = 1.0 - smoothed_t[idx_min]

    centered_z = raw_z - z_focus

    # 5. Math & Physics Calculations
    wavelength_cm = params['wavelength'] * 1e-7
    energy_j = params['energy'] * 1e-9
    pulse_s = params['pulse'] * 1e-15
    w0_cm = params['waist'] * 1e-4
    L_cm = params['thickness'] * 1e-1

    # Peak Intensity (I0) in W/cm^2
    i0 = energy_j / (np.pi * (w0_cm**2) * pulse_s)
    
    if mode == "Closed Aperture (n2)":
        # Calculate Nonlinear Refractive Index (n2)
        coeff = (delta_t * wavelength_cm) / (0.203 * 2 * np.pi * i0)
        coeff_name = "n₂ (cm²/W)"
    else:
        # Calculate Nonlinear Absorption (Beta) using the simplified two-photon absorption valley equation
        coeff = (2 * np.sqrt(2) * delta_t) / (i0 * L_cm)
        coeff_name = "β (cm/W)"

    # 6. Plotting
    fig, ax = plt.subplots(figsize=(10, 6))
    ax.plot(centered_z, normalized_t, marker='o', linestyle='', color='gray', markersize=4, alpha=0.4, label='Raw Data')
    
    line_color = 'blue' if mode == "Closed Aperture (n2)" else 'red'
    ax.plot(centered_z, smoothed_t, linestyle='-', color=line_color, linewidth=2, label='Smoothed Curve')
    
    # Draw lines showing the Delta T extraction points
    if mode == "Closed Aperture (n2)":
        ax.axhline(smoothed_t[idx_max], color='green', linestyle=':', alpha=0.6)
        ax.axhline(smoothed_t[idx_min], color='green', linestyle=':', alpha=0.6)
    else:
        ax.axhline(1.0, color='green', linestyle=':', alpha=0.6)
        ax.axhline(smoothed_t[idx_min], color='green', linestyle=':', alpha=0.6)

    ax.set_title(f'{mode.split(" ")[0]} Z-Scan: {file_name}')
    ax.set_xlabel('Relative Distance z (mm)') 
    ax.set_ylabel('Normalized Transmittance')
    ax.grid(True, linestyle='--', alpha=0.7)
    ax.legend()
    fig.tight_layout()
    
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=300)
    buf.seek(0)
    plt.close(fig)
    
    return {"buffer": buf, "delta_t": delta_t, "i0": i0, "coeff": coeff, "coeff_name": coeff_name}


# --- Streamlit Dashboard UI ---
st.set_page_config(page_title="Ultimate Z-Scan Analyzer", layout="wide")

st.title("⚡ Ultimate Z-Scan Analyzer")
st.markdown("Automated processing, baseline normalization, and coefficient extraction for fs-laser experiments.")

# --- Sidebar Configuration ---
st.sidebar.header("1. Analysis Mode")
analysis_mode = st.sidebar.radio("Select Experiment Type:", ["Closed Aperture (n2)", "Open Aperture (β)"])

st.sidebar.header("2. Laser & Sample Params")
params = {
    "wavelength": st.sidebar.number_input("Wavelength (nm)", value=780.0, step=1.0),
    "energy": st.sidebar.number_input("Pulse Energy (nJ)", value=0.8, step=0.1, format="%.2f"),
    "pulse": st.sidebar.number_input("Pulse FWHM (fs)", value=100.0, step=1.0),
    "waist": st.sidebar.number_input("Beam Waist w₀ (µm)", value=18.0, step=1.0),
    "thickness": st.sidebar.number_input("Sample Thickness (mm)", value=1.0, step=0.1)
}

st.sidebar.header("3. Filter Settings")
params["smooth_window"] = st.sidebar.slider("Smoothing Strength", min_value=3, max_value=31, value=11, step=2)

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
                    # Beautiful Metric Display
                    m1, m2, m3 = st.columns(3)
                    m1.metric("ΔT Extracted", f"{result['delta_t']:.4f}")
                    m2.metric("Peak Intensity (I₀)", f"{result['i0']:.2e} W/cm²")
                    m3.metric(result['coeff_name'], f"{result['coeff']:.4e}")
                    
                    st.divider()
                    
                    left_col, mid_col, right_col = st.columns([1, 2, 1])
                    with mid_col:
                        st.image(result['buffer'], use_container_width=True)
                        png_filename = f"{file_name.split('.')[0]}_{analysis_mode[:6]}.png"
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
        st.caption("Download all generated plots from the current tab stack as a single ZIP archive.")
    with right:
        st.download_button(
            label="Download All Plots (ZIP)",
            data=zip_buffer,
            file_name=f"ZScan_Plots_{analysis_mode[:6]}.zip",
            mime="application/zip",
            type="primary",
            use_container_width=True
        )
