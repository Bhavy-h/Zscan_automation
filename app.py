import streamlit as st
import matplotlib.pyplot as plt
import io
import zipfile
import numpy as np
from scipy.signal import savgol_filter

def process_and_plot(file_content, file_name):
    lines = file_content.decode('utf-8').splitlines()
    distances = []
    voltages = []
    
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

    # Convert to numpy arrays for math operations
    dist_arr = np.array(distances)
    volt_arr = np.array(voltages)
    
    # Sort the data by distance just in case it was recorded out of order
    sort_indices = np.argsort(dist_arr)
    dist_arr = dist_arr[sort_indices]
    volt_arr = volt_arr[sort_indices]

    # --- Apply Savitzky-Golay smoothing filter ---
    # Window length must be an odd number. We'll use 11 as a standard default.
    window_len = min(11, len(dist_arr) - (0 if len(dist_arr) % 2 != 0 else 1))
    if window_len < 3: 
        window_len = 3 
        
    try:
        smoothed_voltages = savgol_filter(volt_arr, window_length=window_len, polyorder=3)
    except Exception:
        # Fallback to raw data if filtering fails (e.g., not enough data points)
        smoothed_voltages = volt_arr

    # Create the plot
    fig, ax = plt.subplots(figsize=(10, 6))
    
    # Plot raw data as faint background dots
    ax.plot(dist_arr, volt_arr, marker='o', linestyle='', color='gray', markersize=4, alpha=0.4, label='Raw Data')
    
    # Plot the smoothed curve on top
    ax.plot(dist_arr, smoothed_voltages, linestyle='-', color='blue', linewidth=2, label='Smoothed Curve')
    
    ax.set_title(f'Z-Scan Measurement: {file_name}')
    ax.set_xlabel('Distance (mm)') 
    ax.set_ylabel('Voltage (V)')
    ax.grid(True, linestyle='--', alpha=0.7)
    ax.legend()
    fig.tight_layout()
    
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=300)
    buf.seek(0)
    
    plt.close(fig)
    return buf

# --- Streamlit Dashboard UI ---
st.set_page_config(page_title="Z-Scan Data Plotter", layout="wide")

st.title("Z-Scan Data Plotter")
st.write("Upload your data files (LabVIEW or comma-separated) to generate and download the plots.")

uploaded_files = st.file_uploader("Choose data files", type=["txt", "csv", "dat"], accept_multiple_files=True)

if uploaded_files:
    st.success(f"{len(uploaded_files)} file(s) uploaded successfully!")
    
    zip_buffer = io.BytesIO()
    tab_names = [file.name for file in uploaded_files]
    tabs = st.tabs(tab_names)
    
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
        
        for i, (uploaded_file, tab) in enumerate(zip(uploaded_files, tabs)):
            file_name = uploaded_file.name
            file_content = uploaded_file.read()
            
            try:
                image_buffer = process_and_plot(file_content, file_name)
                
                with tab:
                    st.subheader(f"Plot Preview")
                    
                    left_col, mid_col, right_col = st.columns([1, 2, 1])
                    
                    with mid_col:
                        st.image(image_buffer, use_container_width=True)
                        
                        png_filename = f"{file_name.split('.')[0]}_plot.png"
                        st.download_button(
                            label=f"Download {file_name} Plot",
                            data=image_buffer,
                            file_name=png_filename,
                            mime="image/png",
                            key=f"download_btn_{i}"
                        )
                
                zip_file.writestr(png_filename, image_buffer.getvalue())
                
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
