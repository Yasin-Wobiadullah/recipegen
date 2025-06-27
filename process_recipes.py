import os
import json
import asyncio
import uuid
from dotenv import load_dotenv
from supabase import create_client, Client
import fal_client
import httpx
from PIL import Image
import io

# --- Configuration ---
load_dotenv() # Load variables from .env file

# Fal.ai model and parameters
FAL_MODEL_ID = "fal-ai/flux-1/schnell/redux"
FAL_PARAMS = {
    "image_size": {"width": 1000, "height": 1000},
    "num_inference_steps": 1,
    "num_images": 1,
    "enable_safety_checker": False
}

# Supabase configuration
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
SUPABASE_BUCKET = os.getenv("SUPABASE_BUCKET_NAME", "images")

# Local file paths
RECIPES_METADATA_FILE = "scraped_recipes.json"
RECIPES_DIR = "recipes"

# --- Initialization ---
try:
    supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
except Exception as e:
    print(f"Error initializing Supabase client: {e}")
    print("Please ensure SUPABASE_URL and SUPABASE_KEY are set correctly in your .env file.")
    exit()

async def process_recipe(recipe: dict, httpx_client: httpx.AsyncClient):
    """Handles the full processing pipeline for a single recipe asynchronously."""
    recipe_title = recipe.get('title', 'Untitled')
    source_image_url = recipe.get('image_url')
    recipe_slug = recipe.get('slug')

    print(f"Processing: {recipe_title}")

    try:
        # 1. Submit job to Fal.ai
        print(f"  - Submitting to Fal.ai for '{recipe_title}'")
        handler = fal_client.submit(FAL_MODEL_ID, arguments={"image_url": source_image_url, **FAL_PARAMS})
        
        # 2. Wait for the result (this blocks but we run it in a thread to not block asyncio event loop)
        result = await asyncio.to_thread(handler.get)
        generated_image_url = result['images'][0]['url']

        # 3. Download the generated image
        print(f"  - Downloading generated image for '{recipe_title}'")
        response = await httpx_client.get(generated_image_url)
        response.raise_for_status()
        image_bytes = response.content

        # 4. Convert to WebP in memory
        print(f"  - Converting to WebP for '{recipe_title}'")
        with Image.open(io.BytesIO(image_bytes)) as img:
            with io.BytesIO() as output_buffer:
                img.save(output_buffer, format="WEBP", quality=85)
                webp_bytes = output_buffer.getvalue()

        # 5. Upload to Supabase
        upload_path = f"{recipe_slug}.webp"
        print(f"  - Uploading to Supabase at '{upload_path}'")
        supabase.storage.from_(SUPABASE_BUCKET).upload(
            path=upload_path,
            file=webp_bytes,
            file_options={"content-type": "image/webp", "upsert": "true"}
        )
        public_url_data = supabase.storage.from_(SUPABASE_BUCKET).get_public_url(upload_path)
        supabase_image_url = public_url_data

        # 6. Update the local recipe JSON file
        recipe_json_path = os.path.join(RECIPES_DIR, f"{recipe_slug}.json")
        print(f"  - Updating local file: {recipe_json_path}")
        with open(recipe_json_path, 'r+') as f:
            data = json.load(f)
            data['generated_image_url'] = supabase_image_url
            f.seek(0)
            json.dump(data, f, indent=2)
            f.truncate()

        print(f"✅ Successfully processed: {recipe_title}")
        return supabase_image_url

    except Exception as e:
        print(f"❌ Error processing '{recipe_title}': {e}")
        return None

async def main():
    """Main function to orchestrate the batch processing."""
    if not os.path.isdir(RECIPES_DIR):
        print(f"Error: Recipes directory not found at '{RECIPES_DIR}'")
        print("Please run the recipe_scraper.py script first.")
        return

    all_recipe_files = [os.path.join(RECIPES_DIR, f) for f in os.listdir(RECIPES_DIR) if f.endswith('.json')]

    # Load and filter recipes
    recipes_to_process = []
    recipes_missing_image = []
    already_processed_count = 0

    for recipe_path in all_recipe_files:
        try:
            with open(recipe_path, 'r') as f:
                recipe = json.load(f)
                # Check if already processed
                if 'generated_image_url' in recipe and recipe['generated_image_url']:
                    already_processed_count += 1
                    continue
                # Check for source image
                if recipe.get('image_url') and recipe.get('slug'):
                    recipes_to_process.append(recipe)
                else:
                    recipes_missing_image.append(recipe.get('title', 'Untitled Recipe'))
        except (json.JSONDecodeError, IOError) as e:
            print(f"Warning: Could not read or parse {recipe_path}. Skipping. Error: {e}")

    print(f"Found {len(all_recipe_files)} total recipe files.")
    print(f"- {already_processed_count} are already processed.")
    print(f"- {len(recipes_missing_image)} are missing a source image URL.")
    print(f"- {len(recipes_to_process)} new recipes to process.")

    if not recipes_to_process:
        print("\nNo new recipes to process. Exiting.")
        return

    # Create a single httpx client for all requests
    async with httpx.AsyncClient(timeout=60.0) as httpx_client:
        tasks = [process_recipe(recipe, httpx_client) for recipe in recipes_to_process]
        results = await asyncio.gather(*tasks)

    print("\n--- Batch Processing Complete ---")
    successful_count = sum(1 for r in results if r is not None)
    print(f"Successfully generated and uploaded {successful_count} new images.")

    if recipes_missing_image:
        print("\nThe following recipes were skipped because they had no source image URL:")
        for title in recipes_missing_image:
            print(f"- {title}")

if __name__ == "__main__":
    # Check for API keys before running
    if not all([os.getenv("FAL_KEY"), SUPABASE_URL, SUPABASE_KEY]):
        print("Error: Missing required environment variables.")
        print("Please create a .env file and set FAL_KEY, SUPABASE_URL, and SUPABASE_KEY.")
    else:
        asyncio.run(main())
