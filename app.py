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
    
    # Close the figure to free up memory (important when looping multiple files)
    plt.close(fig)
    return buf

# --- Streamlit Dashboard UI ---
st.set_page_config(page_title="Z-Scan Data Plotter", layout="centered")

st.title("Z-Scan Data Plotter")
st.write("Upload your data files (LabVIEW or comma-separated) to generate and download the plots.")

# File Uploader - Now accepts multiple files
uploaded_files = st.file_uploader("Choose data files", type=["txt", "csv", "dat"], accept_multiple_files=True)

if uploaded_files:
    st.success(f"{len(uploaded_files)} file(s) uploaded successfully!")
    
    # Loop through the list of uploaded files
    for i, uploaded_file in enumerate(uploaded_files):
        file_name = uploaded_file.name
        file_content = uploaded_file.read()
        
        st.subheader(f"Plot for: {file_name}")
        
        try:
            # Process the file and generate the plot buffer
            image_buffer = process_and_plot(file_content, file_name)
            
            # Display a preview of the plot on the dashboard
            st.image(image_buffer, use_container_width=True)
            
            # Provide the download button (Note the unique 'key' required for buttons in a loop)
            st.download_button(
                label=f"Download {file_name} Plot",
                data=image_buffer,
                file_name=f"{file_name.split('.')[0]}_plot.png",
                mime="image/png",
                key=f"download_btn_{i}"
            )
        except Exception as e:
            st.error(f"An error occurred while processing {file_name}: {e}")
            
        # Add a visual divider between files
        st.markdown("---")
