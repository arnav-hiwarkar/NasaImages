import os
import re
import asyncio
import aiohttp
import requests
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlparse

NASA_SEARCH_API = "https://images-api.nasa.gov/search"
NASA_ASSET_API = "https://images-api.nasa.gov/asset"

DOWNLOAD_DIR = "nasa_wallpapers"
MAX_IMAGES = 200         
MAX_CONCURRENT_REQUESTS = 20   
REQUEST_TIMEOUT = 60


HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
}


def sanitize_filename(name):
    return re.sub(r'[<>:"/\\|?*]', "_", name)[:150] 


def get_search_results(query, max_images=20):
    params = {"q": query, "media_type": "image"}
    response = requests.get(NASA_SEARCH_API, params=params, headers=HEADERS, timeout=30)
    response.raise_for_status()
    items = response.json()["collection"]["items"]
    return items[:max_images]


def get_highest_resolution_asset_sync(nasa_id):
    try:
        response = requests.get(f"{NASA_ASSET_API}/{nasa_id}", headers=HEADERS, timeout=30)
        response.raise_for_status()
        data = response.json()
    except Exception as e:
        print(f"  [{nasa_id}] Error fetching asset list: {e}")
        return None

    items = data["collection"]["items"]

    image_urls = [
        item["href"]
        for item in items
        if item["href"].lower().endswith((".jpg", ".jpeg", ".png", ".tif", ".tiff"))
    ]

    if not image_urls:
        return None

   
    image_urls.sort()
    return image_urls[-1]


def unique_filepath(title, extension):
    """Synchronous filesystem check — fine since it's just a stat call, not I/O bound work."""
    filepath = os.path.join(DOWNLOAD_DIR, sanitize_filename(title) + extension)
    counter = 1
    while os.path.exists(filepath):
        filepath = os.path.join(
            DOWNLOAD_DIR, f"{sanitize_filename(title)}_{counter}{extension}"
        )
        counter += 1
    return filepath


async def download_file(session, url, filepath, semaphore):
    async with semaphore:
        try:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=REQUEST_TIMEOUT)) as response:
                response.raise_for_status()
                with open(filepath, "wb") as f:
                    async for chunk in response.content.iter_chunked(8192):
                        if chunk:
                            f.write(chunk)
            return True
        except Exception as e:
            print(f"  Error downloading {url}: {e}")

            if os.path.exists(filepath):
                os.remove(filepath)
            return False


async def process_item(session, item, semaphore, results_list, loop, executor):
    try:
        data = item["data"][0]
        title = data.get("title", "NASA_Image")
        nasa_id = data["nasa_id"]

        
        async with semaphore:
            image_url = await loop.run_in_executor(
                executor, get_highest_resolution_asset_sync, nasa_id
            )

        if not image_url:
            print(f"  [{title}] No downloadable asset found.")
            results_list.append(False)
            return

        extension = os.path.splitext(urlparse(image_url).path)[1] or ".jpg"
        filepath = unique_filepath(title, extension)

        success = await download_file(session, image_url, filepath, semaphore)

        if success:
            print(f"  Saved: {filepath}")
        results_list.append(success)

    except Exception as e:
        print(f"  Error processing item: {e}")
        results_list.append(False)


async def run(query, max_images):
    os.makedirs(DOWNLOAD_DIR, exist_ok=True)

    
    results = get_search_results(query, max_images)
    print(f"Found {len(results)} candidate images.\n")

    semaphore = asyncio.Semaphore(MAX_CONCURRENT_REQUESTS)
    loop = asyncio.get_event_loop()
    executor = ThreadPoolExecutor(max_workers=MAX_CONCURRENT_REQUESTS)

    connector = aiohttp.TCPConnector(limit=MAX_CONCURRENT_REQUESTS)
    async with aiohttp.ClientSession(connector=connector, headers=HEADERS) as session:
        outcomes = []
        tasks = [
            process_item(session, item, semaphore, outcomes, loop, executor)
            for item in results
        ]

        
        await asyncio.gather(*tasks)

        downloaded = sum(1 for o in outcomes if o)
        print(f"\nDownloaded {downloaded} / {len(results)} images.")

    executor.shutdown(wait=True)


def main():
    query = input("Search NASA images for: ").strip()
    try:
        max_images = int(input(f"How many images to fetch (default {MAX_IMAGES}): ").strip() or MAX_IMAGES)
    except ValueError:
        max_images = MAX_IMAGES

    asyncio.run(run(query, max_images))


if __name__ == "__main__":
    main()
