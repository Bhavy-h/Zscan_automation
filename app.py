import streamlit as st
import matplotlib.pyplot as plt
import io
import zipfile

def process_and_plot(file_content, file_name):
    # Decode the uploaded file bytes into readable strings
    lines = file_content.decode('utf-8').splitlines()
    
    distances = []
    voltages = []
    
    # 1. Check if the file is the LabVIEW format with "***End_of_Header***"
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
        
    # 2. Otherwise, treat it as the simple vertical comma-separated format
    else:
        for line in lines:
            if line.strip(): # Skip completely empty lines
                parts = line.split(',')
                if len(parts) >= 2:
                    try:
                        distances.append(float(parts[0].strip()))
                        voltages.append(float(parts[1].strip()))
                    except ValueError:
                        continue

    # Create the plot
    fig, ax = plt.subplots(figsize=(10, 6))
    ax.plot(distances, voltages, marker='o', linestyle='-', color='b', markersize=4)
    
    # Formatting the chart
    ax.set_title(f'Z-Scan Measurement: {file_name}')
    ax.set_xlabel('Distance (mm)') 
    ax.set_ylabel('Voltage (V)')
    ax.grid(True, linestyle='--', alpha=0.7)
    fig.tight_layout()
    
    # Save the figure to an in-memory bytes buffer
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=300)
    buf.seek(0)
    
    # Close the figure to free up memory
    plt.close(fig)
    return buf

# --- Streamlit Dashboard UI ---
# Changed layout to 'wide' so the tabs have more room to breathe
st.set_page_config(page_title="Z-Scan Data Plotter", layout="wide")

st.title("Z-Scan Data Plotter")
st.write("Upload your data files (LabVIEW or comma-separated) to generate and download the plots.")

# File Uploader
uploaded_files = st.file_uploader("Choose data files", type=["txt", "csv", "dat"], accept_multiple_files=True)

if uploaded_files:
    st.success(f"{len(uploaded_files)} file(s) uploaded successfully!")
    
    # Create an in-memory buffer to hold the ZIP file
    zip_buffer = io.BytesIO()
    
    # Dynamically create a list of tabs based on the file names
    tab_names = [file.name for file in uploaded_files]
    tabs = st.tabs(tab_names)
    
    # Open the ZIP file in write mode
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
        
        # Loop through the files AND the generated tabs simultaneously
        for i, (uploaded_file, tab) in enumerate(zip(uploaded_files, tabs)):
            file_name = uploaded_file.name
            file_content = uploaded_file.read()
            
            try:
                # Process the file and generate the plot buffer
                image_buffer = process_and_plot(file_content, file_name)
                
                # --- Everything indented under 'with tab:' goes inside that specific tab ---
                with tab:
                    st.subheader(f"Plot Preview")
                    
                    # Display the plot inside the tab
                    st.image(image_buffer, use_container_width=True)
                    
                    # Provide the individual download button inside the tab
                    png_filename = f"{file_name.split('.')[0]}_plot.png"
                    st.download_button(
                        label=f"Download {file_name} Plot",
                        data=image_buffer,
                        file_name=png_filename,
                        mime="image/png",
                        key=f"download_btn_{i}"
                    )
                
                # Write the PNG buffer directly into our ZIP file (happens in the background)
                zip_file.writestr(png_filename, image_buffer.getvalue())
                
            except Exception as e:
                with tab:
                    st.error(f"An error occurred while processing {file_name}: {e}")
            
    # Move the ZIP buffer's pointer to the beginning so it can be downloaded
    zip_buffer.seek(0)
    
    # Provide the master "Download All" button outside of the tabs (at the bottom)
    st.markdown("---")
    st.markdown("### 📦 Download All Plots")
    st.download_button(
        label="Download All Plots as ZIP",
        data=zip_buffer,
        file_name="all_zscan_plots.zip",
        mime="application/zip",
        type="primary"
    )
