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
import re

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

def slugify(text: str) -> str:
    """Converts a string into a URL-friendly slug."""
    text = text.replace('|', ' ')
    text = text.lower()
    text = re.sub(r'[^a-z0-9\s-]', '', text) # Remove punctuation except spaces and hyphens
    text = re.sub(r'[\s_]+', '-', text) # Replace spaces and underscores with hyphens
    text = re.sub(r'--+', '-', text) # Replace multiple hyphens with a single one
    text = text.strip('-')
    if not text:
        return str(uuid.uuid4()) # Return a unique ID if slug is empty
    return text

async def process_recipe(recipe: dict, recipe_path: str, httpx_client: httpx.AsyncClient, semaphore: asyncio.Semaphore):
    """Handles the full processing pipeline for a single recipe asynchronously."""
    recipe_title = recipe.get('title', 'Untitled')
    source_image_url = recipe.get('image_url')
    recipe_slug = recipe.get('slug')

    print(f"Processing: {recipe_title}")

    MAX_RETRIES = 3
    RETRY_DELAY = 2  # seconds

    async with semaphore:
        for attempt in range(MAX_RETRIES):
            try:
                # 1. Submit job to Fal.ai
                print(f"  - Submitting to Fal.ai for '{recipe_title}'")
                handler = await asyncio.to_thread(
                    fal_client.submit, FAL_MODEL_ID, arguments={"image_url": source_image_url, **FAL_PARAMS}
                )
                result = await asyncio.to_thread(handler.get)

                if not result or 'images' not in result or not result['images']:
                    raise ValueError("Fal.ai returned no images.")

                generated_image_url = result['images'][0]['url']

                # 2. Download the generated image
                print(f"  - Downloading generated image for '{recipe_title}'")
                response = await httpx_client.get(generated_image_url)
                response.raise_for_status()
                image_bytes = response.content

                # 3. Convert to WebP in memory (using a thread for the CPU-bound task)
                print(f"  - Converting to WebP for '{recipe_title}'")
                def convert_to_webp(img_bytes):
                    with Image.open(io.BytesIO(img_bytes)) as img:
                        with io.BytesIO() as output_buffer:
                            img.save(output_buffer, format="WEBP", quality=85)
                            return output_buffer.getvalue()
                webp_bytes = await asyncio.to_thread(convert_to_webp, image_bytes)

                # 4. Upload to Supabase (using a thread for the blocking SDK call)
                upload_path = f"{recipe_slug}.webp"
                print(f"  - Uploading to Supabase at '{upload_path}'")
                await asyncio.to_thread(
                    supabase.storage.from_(SUPABASE_BUCKET).upload,
                    path=upload_path,
                    file=webp_bytes,
                    file_options={"content-type": "image/webp", "upsert": "true"}
                )
                public_url_data = await asyncio.to_thread(
                    supabase.storage.from_(SUPABASE_BUCKET).get_public_url, upload_path
                )
                supabase_image_url = public_url_data

                # 5. Update the local recipe JSON file (using a thread for blocking file I/O)
                print(f"  - Updating local file: {recipe_path}")
                def update_json_file():
                    with open(recipe_path, 'r+') as f:
                        data = json.load(f)
                        data['generated_image_url'] = supabase_image_url
                        f.seek(0)
                        json.dump(data, f, indent=2)
                        f.truncate()
                await asyncio.to_thread(update_json_file)

                print(f"✅ Successfully processed: {recipe_title}")
                return supabase_image_url # Success, exit the retry loop

            except Exception as e:
                if "Resource temporarily unavailable" in str(e) and attempt < MAX_RETRIES - 1:
                    wait_time = RETRY_DELAY * (2 ** attempt)  # Exponential backoff
                    print(f"⏳ Retrying '{recipe_title}' (attempt {attempt + 2}/{MAX_RETRIES}) after {wait_time}s... Error: {e}")
                    await asyncio.sleep(wait_time)
                    continue # Go to the next attempt
                else:
                    print(f"❌ Error processing '{recipe_title}' after {attempt + 1} attempts: {e}")
                    return None # Permanent failure

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
                if 'generated_image_url' in recipe and recipe['generated_image_url']:
                    already_processed_count += 1
                    continue

                # Generate slug from title if it doesn't exist
                if 'slug' not in recipe or not recipe.get('slug'):
                    title = recipe.get('title')
                    if title:
                        recipe['slug'] = slugify(title)

                if recipe.get('image_url') and recipe.get('slug'):
                    recipes_to_process.append((recipe, recipe_path))
                else:
                    recipes_missing_image.append(recipe.get('title', 'Untitled Recipe'))
        except (json.JSONDecodeError, IOError) as e:
            print(f"Warning: Could not read or parse {recipe_path}. Skipping. Error: {e}")

    print(f"Found {len(all_recipe_files)} total recipe files.")
    print(f"- {already_processed_count} are already processed.")
    print(f"- {len(recipes_missing_image)} are missing a source image URL or slug.")
    print(f"- {len(recipes_to_process)} new recipes to process.")

    if not recipes_to_process:
        print("\nNo new recipes to process. Exiting.")
        return

    # Limit concurrency to avoid overwhelming the API service
    CONCURRENT_LIMIT = 10
    semaphore = asyncio.Semaphore(CONCURRENT_LIMIT)

    # Create a single httpx client for all requests
    async with httpx.AsyncClient(timeout=60.0) as httpx_client:
        tasks = [process_recipe(recipe, path, httpx_client, semaphore) for recipe, path in recipes_to_process]
        results = await asyncio.gather(*tasks)

    print("\n--- Batch Processing Complete ---")
    successful_count = sum(1 for r in results if r is not None)
    print(f"Successfully generated and uploaded {successful_count} new images.")

    if recipes_missing_image:
        print("\nThe following recipes were skipped because they had no source image URL or slug:")
        for title in recipes_missing_image:
            print(f"- {title}")

if __name__ == "__main__":
    # Check for API keys before running
    if not all([os.getenv("FAL_KEY"), SUPABASE_URL, SUPABASE_KEY]):
        print("Error: Missing required environment variables.")
        print("Please create a .env file and set FAL_KEY, SUPABASE_URL, and SUPABASE_KEY.")
    else:
        asyncio.run(main())
