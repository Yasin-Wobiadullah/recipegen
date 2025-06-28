import os
import json

# --- Configuration ---
RECIPES_DIR = "recipes"

def find_recipes_to_delete():
    """
    Scans the recipes directory and identifies files missing a source image_url.
    """
    if not os.path.isdir(RECIPES_DIR):
        print(f"Error: Recipes directory not found at '{RECIPES_DIR}'")
        return []

    all_recipe_files = [os.path.join(RECIPES_DIR, f) for f in os.listdir(RECIPES_DIR) if f.endswith('.json')]
    paths_to_delete = []

    print(f"Scanning {len(all_recipe_files)} files...")

    for recipe_path in all_recipe_files:
        try:
            with open(recipe_path, 'r') as f:
                recipe = json.load(f)
                # Check if 'image_url' key is missing, or if it's present but the value is empty/None
                if not recipe.get('image_url'):
                    paths_to_delete.append(recipe_path)
        except (json.JSONDecodeError, IOError) as e:
            print(f"Warning: Could not read or parse {recipe_path}. Skipping. Error: {e}")

    return paths_to_delete

def main():
    """
    Main function to find and delete recipes missing a source image URL.
    """
    print("--- Recipe Cleaner ---")
    files_to_delete = find_recipes_to_delete()

    if not files_to_delete:
        print("\nNo recipes found missing a source image URL. Your dataset is clean!")
        return

    print(f"\nFound {len(files_to_delete)} recipes to delete:")
    # Preview first 10 files to be deleted
    for path in files_to_delete[:10]:
        print(f" - {os.path.basename(path)}")
    if len(files_to_delete) > 10:
        print(f"   ...and {len(files_to_delete) - 10} more.")

    # Confirmation step
    try:
        confirm = input("\nAre you sure you want to permanently delete these files? (y/n): ").lower()
    except KeyboardInterrupt:
        print("\n\nDeletion cancelled by user.")
        return


    if confirm == 'y':
        print("\nDeleting files...")
        deleted_count = 0
        for path in files_to_delete:
            try:
                os.remove(path)
                deleted_count += 1
            except OSError as e:
                print(f"Error deleting {path}: {e}")
        print(f"\nSuccessfully deleted {deleted_count} files.")
    else:
        print("\nDeletion cancelled. No files were changed.")


if __name__ == "__main__":
    main()
