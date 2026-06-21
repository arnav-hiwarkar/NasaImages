import os
import re
import requests
from urllib.parse import urlparse

NASA_SEARCH_API = "https://images-api.nasa.gov/search"
NASA_ASSET_API = "https://images-api.nasa.gov/asset"

DOWNLOAD_DIR = "nasa_wallpapers"
MAX_IMAGES = 20  # Number of images to download


def sanitize_filename(name):
    return re.sub(r'[<>:"/\\|?*]', "_", name)


def get_search_results(query, max_images=20):
    params = {
        "q": query,
        "media_type": "image"
    }

    response = requests.get(NASA_SEARCH_API, params=params, timeout=30)
    response.raise_for_status()

    items = response.json()["collection"]["items"]
    return items[:max_images]


def get_highest_resolution_asset(nasa_id):
    response = requests.get(f"{NASA_ASSET_API}/{nasa_id}", timeout=30)
    response.raise_for_status()

    items = response.json()["collection"]["items"]

    image_urls = [
        item["href"]
        for item in items
        if item["href"].lower().endswith(
            (".jpg", ".jpeg", ".png", ".tif", ".tiff")
        )
    ]

    if not image_urls:
        return None

    # NASA asset listings often contain larger images later in the list.
    image_urls.sort()
    return image_urls[-1]


def download_file(url, filename):
    response = requests.get(url, stream=True, timeout=60)
    response.raise_for_status()

    with open(filename, "wb") as f:
        for chunk in response.iter_content(chunk_size=8192):
            if chunk:
                f.write(chunk)


def main():
    os.makedirs(DOWNLOAD_DIR, exist_ok=True)

    query = input("Search NASA images for: ").strip()

    results = get_search_results(query, MAX_IMAGES)

    print(f"Found {len(results)} candidate images.")

    downloaded = 0

    for item in results:
        try:
            data = item["data"][0]

            title = data.get("title", "NASA_Image")
            nasa_id = data["nasa_id"]

            print(f"Processing: {title}")

            image_url = get_highest_resolution_asset(nasa_id)

            if not image_url:
                print("  No downloadable asset found.")
                continue

            extension = os.path.splitext(
                urlparse(image_url).path
            )[1] or ".jpg"

            filename = sanitize_filename(title) + extension
            filepath = os.path.join(DOWNLOAD_DIR, filename)

            counter = 1
            while os.path.exists(filepath):
                filepath = os.path.join(
                    DOWNLOAD_DIR,
                    f"{sanitize_filename(title)}_{counter}{extension}"
                )
                counter += 1

            download_file(image_url, filepath)

            print(f"  Saved: {filepath}")
            downloaded += 1

        except Exception as e:
            print(f"  Error: {e}")

    print(f"\nDownloaded {downloaded} images.")


if __name__ == "__main__":
    main()
