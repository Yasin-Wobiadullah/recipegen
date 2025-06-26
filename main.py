import requests
from bs4 import BeautifulSoup
import json

SITEMAP_URL = "https://www.seriouseats.com/sitemap_1.xml"
OUTPUT_JSON = "sitemap_data.json"

def fetch_and_save_sitemap_as_json(sitemap_url, output_file):
    print(f"Fetching sitemap from: {sitemap_url}")
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        }
        resp = requests.get(sitemap_url, headers=headers)
        resp.raise_for_status()  # Raise an exception for bad status codes
    except requests.exceptions.RequestException as e:
        print(f"Error fetching sitemap: {e}")
        return

    print("Parsing XML content...")
    soup = BeautifulSoup(resp.content, "xml")
    entries = []
    for url_tag in soup.find_all("url"):
        loc_tag = url_tag.find("loc")
        lastmod_tag = url_tag.find("lastmod")
        changefreq_tag = url_tag.find("changefreq")
        priority_tag = url_tag.find("priority")

        entry = {
            "loc": loc_tag.text if loc_tag else None,
            "lastmod": lastmod_tag.text if lastmod_tag else None,
            "changefreq": changefreq_tag.text if changefreq_tag else None,
            "priority": priority_tag.text if priority_tag else None,
        }
        entries.append(entry)

    print(f"Found {len(entries)} entries in the sitemap.")

    print(f"Saving data to {output_file}...")
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(entries, f, indent=2)
    print("Successfully saved data.")

if __name__ == "__main__":
    fetch_and_save_sitemap_as_json(SITEMAP_URL, OUTPUT_JSON)
