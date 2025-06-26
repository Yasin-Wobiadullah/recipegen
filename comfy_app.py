import os
import subprocess
from pathlib import Path

import modal

# Define the location of our persistent volume
CACHE_PATH = Path("/cache")

# Define a barebones image, we'll install dependencies manually
image = (
    modal.Image.debian_slim(python_version="3.10")
    .apt_install("git")
    .pip_install(
        "comfy-cli",
        "huggingface_hub[hf_transfer]",
        "torch==2.3.1",
        "torchvision==0.18.1",
        "torchaudio==2.3.1",
        extra_index_url="https://download.pytorch.org/whl/cu121",
    )
)

# Create a persistent volume for the ComfyUI installation and models
# NOTE: To force a full reinstall, change the name of the volume.
volume = modal.Volume.from_name("comfyui-flux-cache-v1", create_if_missing=True)

app = modal.App(name="flux-comfyui", image=image)


@app.function(
    # Mount the volume where we'll store everything
    volumes={CACHE_PATH: volume},
    # Standard resource configuration
    max_containers=1,
    scaledown_window=30,
    timeout=1800,
    gpu="a10g",
)
@modal.web_server(8000, startup_timeout=120)
def ui():
    comfyui_path = CACHE_PATH / "ComfyUI"
    success_file = CACHE_PATH / "setup_complete.txt"

    # --- ONE-TIME SETUP --- #
    # If the success file does not exist, we need to run the setup.
    if not success_file.exists():
        print("\n--- Performing one-time setup, this will take a while... ---")

        # 1. Clone the ComfyUI repository
        print("--- 1. Cloning ComfyUI Repo ---")
        subprocess.run(
            f"git clone https://github.com/comfyanonymous/ComfyUI.git {comfyui_path}",
            shell=True,
            check=True,
        )

        # 2. Patch requirements to prevent torch re-installation
        print("--- 2. Patching requirements.txt ---")
        requirements_path = comfyui_path / "requirements.txt"
        # Use sed to remove lines starting with torch, torchvision, or torchaudio
        subprocess.run(
            f"sed -i '/^torch/d' {requirements_path}",
            shell=True,
            check=True,
        )

        # 3. Install ComfyUI's other dependencies
        print("--- 3. Installing ComfyUI Requirements ---")
        subprocess.run(f"pip install -r {requirements_path}", shell=True, check=True)

        # 4. Install ComfyUI-Manager
        print("--- 4. Installing ComfyUI-Manager ---")
        manager_dir = comfyui_path / "custom_nodes" / "ComfyUI-Manager"
        subprocess.run(
            f"git clone https://github.com/ltdrdata/ComfyUI-Manager.git {manager_dir}",
            shell=True,
            check=True,
        )

        # 5. Download models and custom nodes
        print("--- 5. Downloading Models & Custom Nodes ---")
        os.environ["COMFY_USER_CONFIG_DIR"] = str(CACHE_PATH)
        os.environ["COMFYUI_PATH"] = str(comfyui_path)

        download_commands = [
            'comfy --skip-prompt model download --url https://huggingface.co/city96/FLUX.1-dev-gguf/resolve/main/flux1-dev-Q8_0.gguf --relative-path models/unet',
            'comfy --skip-prompt model download --url https://huggingface.co/black-forest-labs/FLUX.1-schnell/resolve/main/ae.safetensors --relative-path models/vae',
            'comfy --skip-prompt model download --url https://huggingface.co/comfyanonymous/flux_text_encoders/resolve/main/clip_l.safetensors --relative-path models/clip',
            'comfy --skip-prompt model download --url https://huggingface.co/comfyanonymous/flux_text_encoders/resolve/main/t5xxl_fp8_e4m3fn.safetensors --relative-path models/clip',
            'comfy node install https://github.com/city96/ComfyUI-GGUF',
            'comfy node install https://github.com/Fannovel16/comfyui_controlnet_aux',
        ]
        for command in download_commands:
            subprocess.run(command, shell=True, check=True)

        # 6. Create success file and commit the volume
        print("--- Setup complete, creating success file. ---")
        success_file.touch()
        volume.commit()

    # --- LAUNCH SERVER --- #
    print("\n--- Launching ComfyUI Server ---")
    subprocess.run(
        "python main.py --listen 0.0.0.0 --port 8000",
        shell=True,
        check=True,
        cwd=comfyui_path,
    )

