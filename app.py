import streamlit as st
import matplotlib.pyplot as plt
import io
import zipfile
import numpy as np
from scipy.signal import savgol_filter

def process_and_plot(file_content, file_name, params):
    lines = file_content.decode('utf-8').splitlines()
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
                parts = line.split(',')
                if len(parts) >= 2:
                    try:
                        distances.append(float(parts[0].strip()))
                        voltages.append(float(parts[1].strip()))
                    except ValueError:
                        continue

    dist_arr = np.array(distances)
    volt_arr = np.array(voltages)
    
    sort_indices = np.argsort(dist_arr)
    dist_arr = dist_arr[sort_indices]
    volt_arr = volt_arr[sort_indices]

    # --- NEW: Normalization and Math ---
    # Normalize voltage to Transmittance (T) by using the first 5% and last 5% of points as the baseline (linear region)
    edge_points = max(3, int(len(volt_arr) * 0.05))
    baseline_v = (np.mean(volt_arr[:edge_points]) + np.mean(volt_arr[-edge_points:])) / 2
    normalized_t = volt_arr / baseline_v

    window_len = min(11, len(dist_arr) - (0 if len(dist_arr) % 2 != 0 else 1))
    if window_len < 3: window_len = 3 
        
    try:
        smoothed_t = savgol_filter(normalized_t, window_length=window_len, polyorder=3)
    except Exception:
        smoothed_t = normalized_t

    # Extract Peak-to-Valley difference from the smoothed curve to avoid noise spikes
    delta_t = np.max(smoothed_t) - np.min(smoothed_t)

    # Convert parameters to standard scientific units (cm, Joules, seconds)
    wavelength_cm = params['wavelength'] * 1e-7
    energy_j = params['energy'] * 1e-9
    pulse_s = params['pulse'] * 1e-15
    w0_cm = params['waist'] * 1e-4

    # Calculate Peak Intensity (I0) and Nonlinear Refractive Index (n2)
    i0 = energy_j / (np.pi * (w0_cm**2) * pulse_s)
    n2 = (delta_t * wavelength_cm) / (0.203 * 2 * np.pi * i0)

    # --- Plotting ---
    fig, ax = plt.subplots(figsize=(10, 6))
    ax.plot(dist_arr, normalized_t, marker='o', linestyle='', color='gray', markersize=4, alpha=0.4, label='Raw Data')
    ax.plot(dist_arr, smoothed_t, linestyle='-', color='blue', linewidth=2, label='Smoothed Curve')
    
    ax.set_title(f'Normalized Z-Scan Measurement: {file_name}')
    ax.set_xlabel('Distance (mm)') 
    ax.set_ylabel('Normalized Transmittance')
    ax.grid(True, linestyle='--', alpha=0.7)
    ax.legend()
    fig.tight_layout()
    
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=300)
    buf.seek(0)
    plt.close(fig)
    
    # Return a dictionary containing the plot and the calculated metrics
    return {"buffer": buf, "delta_t": delta_t, "i0": i0, "n2": n2}

# --- Streamlit Dashboard UI ---
st.set_page_config(page_title="Z-Scan Data Plotter", layout="wide")

st.title("Z-Scan Data Plotter & Analyzer")

# --- NEW: Sidebar for Laser Parameters ---
st.sidebar.header("Laser Parameters")
st.sidebar.write("Adjust these to match your experimental setup.")

# Default values are pulled directly from your legacy MATLAB scripts
params = {
    "wavelength": st.sidebar.number_input("Wavelength (nm)", value=780.0, step=1.0),
    "energy": st.sidebar.number_input("Pulse Energy (nJ)", value=0.8, step=0.1, format="%.2f"),
    "pulse": st.sidebar.number_input("Pulse FWHM (fs)", value=100.0, step=1.0),
    "waist": st.sidebar.number_input("Beam Waist w0 (µm)", value=18.0, step=1.0)
}

uploaded_files = st.file_uploader("Choose data files", type=["txt", "csv", "dat"], accept_multiple_files=True)

if uploaded_files:
    zip_buffer = io.BytesIO()
    tab_names = [file.name for file in uploaded_files]
    tabs = st.tabs(tab_names)
    
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
        for i, (uploaded_file, tab) in enumerate(zip(uploaded_files, tabs)):
            file_name = uploaded_file.name
            file_content = uploaded_file.read()
            
            try:
                # Pass the parameters dictionary to the processing function
                result = process_and_plot(file_content, file_name, params)
                
                with tab:
                    # --- NEW: Display the calculated metrics beautifully ---
                    m1, m2, m3 = st.columns(3)
                    m1.metric("ΔT (Peak-to-Valley)", f"{result['delta_t']:.4f}")
                    m2.metric("Peak Intensity (I0)", f"{result['i0']:.2e} W/cm²")
                    m3.metric("n2 Coefficient", f"{result['n2']:.4e} cm²/W")
                    
                    st.divider()
                    
                    # Display the plot
                    left_col, mid_col, right_col = st.columns([1, 2, 1])
                    with mid_col:
                        st.image(result['buffer'], use_container_width=True)
                        png_filename = f"{file_name.split('.')[0]}_plot.png"
                        st.download_button(
                            label=f"Download {file_name} Plot",
                            data=result['buffer'],
                            file_name=png_filename,
                            mime="image/png",
                            key=f"download_btn_{i}"
                        )
                
                zip_file.writestr(png_filename, result['buffer'].getvalue())
                
            except Exception as e:
                with tab:
                    st.error(f"An error occurred while processing {file_name}: {e}")
            
    zip_buffer.seek(0)
    
    st.markdown("---")
    st.markdown("### 📦 Download All Plots")
    st.download_button(
        label="Download All Plots as ZIP",
        data=zip_buffer,
        file_name="all_zscan_plots.zip",
        mime="application/zip",
        type="primary"
    )
