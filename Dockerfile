# Use an official PyTorch image with CUDA 12.1 as a base
# This ensures PyTorch and CUDA are correctly pre-installed.
FROM pytorch/pytorch:2.3.1-cuda12.1-cudnn8-runtime

# Set the working directory inside the container
WORKDIR /app

# Install system dependencies like git and wget
RUN apt-get update && apt-get install -y \
    git \
    wget \
    && rm -rf /var/lib/apt/lists/*

# Clone the ComfyUI repository
RUN git clone https://github.com/comfyanonymous/ComfyUI.git

# Set the working directory to the ComfyUI folder
WORKDIR /app/ComfyUI

# Remove torch from requirements to avoid conflicts with the base image
RUN sed -i '/^torch/d' requirements.txt

# Install ComfyUI's Python dependencies
RUN pip install -r requirements.txt

# --- Download Models ---
# Create directories for the models
RUN mkdir -p models/unet models/clip models/vae

# Download FLUX models
RUN wget -O models/unet/flux1-dev-Q8_0.gguf https://huggingface.co/city96/FLUX.1-dev-gguf/resolve/main/flux1-dev-Q8_0.gguf
RUN wget -O models/clip/clip_l.safetensors https://huggingface.co/comfyanonymous/flux_text_encoders/resolve/main/clip_l.safetensors
RUN wget -O models/clip/t5xxl_fp8_e4m3fn.safetensors https://huggingface.co/comfyanonymous/flux_text_encoders/resolve/main/t5xxl_fp8_e4m3fn.safetensors
RUN wget -O models/vae/ae.safetensors https://huggingface.co/black-forest-labs/FLUX.1-schnell/resolve/main/ae.safetensors

# --- Install Custom Nodes ---
WORKDIR /app/ComfyUI/custom_nodes

# Install ComfyUI-Manager (useful for managing nodes later)
RUN git clone https://github.com/ltdrdata/ComfyUI-Manager.git

# Install the GGUF node required for the FLUX model
RUN git clone https://github.com/city96/ComfyUI-GGUF.git

# Install ControlNet Aux Preprocessors (often useful)
RUN git clone https://github.com/Fannovel16/comfyui_controlnet_aux.git

# Return to the main ComfyUI directory
WORKDIR /app/ComfyUI

# Expose the ComfyUI port
EXPOSE 8188

# The command to run when the container starts.
# '--listen 0.0.0.0' is crucial for making it accessible outside the container.
CMD ["python", "main.py", "--listen", "0.0.0.0"]
