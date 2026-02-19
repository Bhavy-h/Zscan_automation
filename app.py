import streamlit as st
import matplotlib.pyplot as plt
import io

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
                        # Skip lines that contain non-numeric text
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
    return buf

# --- Streamlit Dashboard UI ---
st.set_page_config(page_title="Z-Scan Data Plotter", layout="centered")

st.title("Z-Scan Data Plotter")
st.write("Upload your data file (LabVIEW or comma-separated) to generate and download the plot.")

# File Uploader - Now accepts general text/csv extensions
uploaded_file = st.file_uploader("Choose a data file", type=["txt", "csv", "dat"])

if uploaded_file is not None:
    file_name = uploaded_file.name
    file_content = uploaded_file.read()
    
    try:
        # Process the file and generate the plot buffer
        image_buffer = process_and_plot(file_content, file_name)
        
        st.success("Plot generated successfully!")
        
        # Display a preview of the plot on the dashboard
        st.image(image_buffer, caption="Preview of your plot", use_container_width=True)
        
        # Provide the download button
        st.download_button(
            label="Download Plot as PNG",
            data=image_buffer,
            file_name=f"{file_name.split('.')[0]}_plot.png",
            mime="image/png"
        )
    except Exception as e:
        st.error(f"An error occurred while processing the file: {e}")
        st.write("Please ensure the uploaded file matches one of the expected formats.")
