import argparse
import requests
import time

# --- Argument Parsing ---
parser = argparse.ArgumentParser(description="Client to run ComfyUI inference on Modal.")
parser.add_argument(
    "--prompt",
    type=str,
    required=True,
    help="The text prompt for image generation.",
)
parser.add_argument(
    "--url",
    type=str,
    required=True,
    help="The URL of the deployed Modal web endpoint.",
)
parser.add_argument(
    "--output",
    type=str,
    default="output.png",
    help="The filename to save the output image to.",
)
args = parser.parse_args()

# --- Main Execution ---
if __name__ == "__main__":
    print(f"Sending prompt: '{args.prompt}' to {args.url}")
    
    payload = {"prompt": args.prompt}
    headers = {"Content-Type": "application/json"}

    start_time = time.time()
    try:
        response = requests.post(args.url, json=payload, headers=headers)
        response.raise_for_status()  # Raise an exception for bad status codes (4xx or 5xx)
        
        # Save the image
        with open(args.output, "wb") as f:
            f.write(response.content)
        
        end_time = time.time()
        print(f"✅ Success! Image saved to {args.output} in {end_time - start_time:.2f} seconds.")

    except requests.exceptions.RequestException as e:
        print(f"❌ An error occurred: {e}")
