import requests
from bs4 import BeautifulSoup
import json
import time
import os

def scrape_recipe(session, url):
    """
    Scrapes a single recipe URL.
    It fetches the main page for image/tags and the print page for text content.
    """
    print(f"Scraping URL: {url}")
    try:
        # --- 1. GET Request to the main page ---
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        }
        main_page_resp = session.get(url, headers=headers)
        main_page_resp.raise_for_status()
        main_soup = BeautifulSoup(main_page_resp.content, 'html.parser')

        # --- 2. Confirm it's a recipe ---
        recipe_box = main_soup.find('div', class_='recipe-decision-block')
        if not recipe_box:
            print("  -> Not a recipe page (missing recipe-decision-block). Skipping.")
            return None

        # --- 3. Extract from Main Page (Image, Tags, Form Data) ---
        # Image URL
        image_url = None
        primary_image_figure = main_soup.find('figure', class_='primary-image')
        if primary_image_figure:
            img_tag = primary_image_figure.find('img')
            if img_tag and img_tag.get('src'):
                image_url = img_tag['src']

        # Tags
        tags = []
        tag_container = main_soup.find('div', class_='content-tax-cloud-tag-nav')
        if tag_container:
            tag_links = tag_container.find_all('a')
            tags = [link.text.strip() for link in tag_links]

        # Print Form Data
        print_form = main_soup.find('form', id=lambda x: x and x.startswith('recipe-decision-block__print-button'))
        if not print_form:
            print("  -> Could not find print button form. Skipping.")
            return None

        action_url_suffix = print_form['action']
        action_url = f"https://www.seriouseats.com{action_url_suffix}"
        csrf_token = print_form.find('input', {'name': 'CSRFToken'})
        if not csrf_token:
            print("  -> Could not find CSRF token. Skipping.")
            return None
        csrf_value = csrf_token['value']

        # --- 4. POST Request to get printable page ---
        print_page_resp = session.post(action_url, data={'CSRFToken': csrf_value}, headers=headers)
        print_page_resp.raise_for_status()
        print_soup = BeautifulSoup(print_page_resp.content, 'html.parser')

        # --- 5. Simplified Extraction from Print Page ---
        recipe_data = {
            'url': url,
            'image_url': image_url,
            'tags': tags,
            'title': None,
            'full_text': None
        }

        # Title
        title_tag = print_soup.find('h1', class_='heading__title')
        recipe_data['title'] = title_tag.text.strip() if title_tag else "Untitled"

        # Full Text
        content_container = print_soup.find('div', class_='loc content')
        if content_container:
            # Use get_text with a separator to preserve line breaks
            recipe_data['full_text'] = content_container.get_text(separator='\n', strip=True)
        
        print(f"  -> Successfully scraped: {recipe_data['title']}")
        return recipe_data

    except requests.exceptions.RequestException as e:
        print(f"  -> Error fetching {url}: {e}")
        return None
    except Exception as e:
        print(f"  -> An unexpected error occurred for {url}: {e}")
        return None

def main():
    # Load URLs from the sitemap data
    try:
        with open('sitemap_data.json', 'r') as f:
            sitemap_urls = [item['loc'] for item in json.load(f)]
    except FileNotFoundError:
        print("Error: sitemap_data.json not found. Please run main.py first.")
        return

    # Create the output directory if it doesn't exist
    output_dir = 'recipes'
    os.makedirs(output_dir, exist_ok=True)
    print(f"Saving recipes to '{output_dir}/' directory.")

    # Process all URLs from the sitemap
    urls_to_scrape = sitemap_urls
    print(f"--- Starting full scrape for {len(urls_to_scrape)} URLs ---")

    new_recipes_found = 0
    with requests.Session() as session:
        for url in urls_to_scrape:
            # Generate a clean filename from the URL slug
            slug = url.strip('/').split('/')[-1]
            if not slug:
                slug = f"recipe_{hash(url)}"
            filename = f"{slug}.json"
            filepath = os.path.join(output_dir, filename)

            # Check if file already exists to make the script resumable
            if os.path.exists(filepath):
                # Silently skip already scraped files in the full run
                continue

            recipe = scrape_recipe(session, url)
            if recipe:
                # Save the recipe to its own file
                with open(filepath, 'w', encoding='utf-8') as f:
                    json.dump(recipe, f, indent=2)
                new_recipes_found += 1
            
            # No delay as per user request

    print(f"\n--- Scraping complete. Found {new_recipes_found} new recipes. ---")

if __name__ == '__main__':
    main()
