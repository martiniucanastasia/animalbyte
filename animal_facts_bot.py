#!/usr/bin/env python3
"""
Daily Animal Facts Telegram Bot
Posts an interesting animal fact with photos to a Telegram channel.
"""

from typing import Optional, List

import requests
import urllib3
import json
import sys
import os
from datetime import datetime
from pathlib import Path

# Suppress SSL warnings (macOS LibreSSL compatibility)
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

SESSION = requests.Session()
SESSION.verify = False
SESSION.headers.update({
    "User-Agent": "AnimalFactsBot/1.0 (https://github.com; contact@example.com)"
})

# ── Config ────────────────────────────────────────────────────────────────────
CONFIG_FILE = Path(__file__).parent / "config.json"

def load_config():
    # GitHub Actions: read from environment variables
    if os.environ.get("BOT_TOKEN"):
        return {
            "bot_token": os.environ["BOT_TOKEN"],
            "channel_id": os.environ["CHANNEL_ID"],
        }
    # Local: read from config.json
    if not CONFIG_FILE.exists():
        print("ERROR: config.json not found")
        sys.exit(1)
    with open(CONFIG_FILE) as f:
        return json.load(f)

# ── Animal list (80 fascinating creatures) ────────────────────────────────────
ANIMALS = [
    "African elephant", "Lion", "Tiger", "Cheetah", "Leopard",
    "Snow leopard", "Jaguar", "Giraffe", "Hippopotamus", "White rhinoceros",
    "Zebra", "Gorilla", "Chimpanzee", "Orangutan", "Bonobo",
    "Giant panda", "Polar bear", "Brown bear", "Gray wolf", "Arctic fox",
    "Red fox", "Meerkat", "Fennec fox", "Capybara", "Giant anteater",
    "Bottlenose dolphin", "Humpback whale", "Blue whale", "Orca", "Sperm whale",
    "Narwhal", "Beluga whale", "Manatee", "Walrus", "Harbour seal",
    "Great white shark", "Hammerhead shark", "Whale shark", "Manta ray", "Octopus",
    "Giant squid", "Mantis shrimp", "Clownfish", "Seahorse", "Leafy sea dragon",
    "Emperor penguin", "Bald eagle", "Peregrine falcon", "Flamingo", "Peacock",
    "Toucan", "Scarlet macaw", "Barn owl", "Wandering albatross", "Ostrich",
    "Lyrebird", "Kiwi", "Cassowary", "Atlantic puffin", "Resplendent quetzal",
    "Komodo dragon", "Saltwater crocodile", "Green anaconda", "Chameleon", "Blue-tongued skink",
    "Axolotl", "Poison dart frog", "Red-eyed tree frog", "Glass frog", "Goliath frog",
    "Monarch butterfly", "Honey bee", "Praying mantis", "Atlas moth", "Goliath birdeater",
    "Platypus", "Kangaroo", "Koala", "Wombat", "Tasmanian devil",
    "Sloth", "Armadillo", "Pangolin", "Okapi", "Proboscis monkey",
]

# ── Animal emoji map ───────────────────────────────────────────────────────────
EMOJI_MAP = {
    "lion": "🦁", "tiger": "🐯", "elephant": "🐘", "giraffe": "🦒",
    "penguin": "🐧", "dolphin": "🐬", "whale": "🐋", "shark": "🦈",
    "polar bear": "🐻‍❄️", "bear": "🐻", "panda": "🐼", "fox": "🦊",
    "wolf": "🐺", "eagle": "🦅", "owl": "🦉", "flamingo": "🦩",
    "peacock": "🦚", "parrot": "🦜", "macaw": "🦜", "toucan": "🦜",
    "snake": "🐍", "anaconda": "🐍", "crocodile": "🐊", "turtle": "🐢",
    "frog": "🐸", "octopus": "🐙", "crab": "🦀", "butterfly": "🦋",
    "bee": "🐝", "kangaroo": "🦘", "koala": "🐨", "gorilla": "🦍",
    "chimpanzee": "🐒", "monkey": "🐒", "sloth": "🦥", "platypus": "🦆",
    "seahorse": "🐠", "clownfish": "🐠", "mantis": "🦗", "puffin": "🐦",
    "ostrich": "🦢", "cheetah": "🐆", "leopard": "🐆", "jaguar": "🐆",
    "rhinoceros": "🦏", "hippopotamus": "🦛", "zebra": "🦓", "capybara": "🐁",
    "narwhal": "🦄", "manatee": "🐋", "walrus": "🐘", "armadillo": "🐾",
    "pangolin": "🐾", "okapi": "🦒",
}

def get_emoji(animal: str) -> str:
    animal_lower = animal.lower()
    for key, em in EMOJI_MAP.items():
        if key in animal_lower:
            return em
    return "🌿"

# ── Select today's animal ──────────────────────────────────────────────────────
def get_animal_of_the_day() -> str:
    day = datetime.now().timetuple().tm_yday
    year = datetime.now().year
    index = (day + year * 100) % len(ANIMALS)
    return ANIMALS[index]

# ── Wikipedia helpers ──────────────────────────────────────────────────────────
def get_wikipedia_summary(animal: str) -> Optional[dict]:
    slug = animal.replace(" ", "_")
    url = f"https://en.wikipedia.org/api/rest_v1/page/summary/{slug}"
    try:
        r = SESSION.get(url, timeout=10, verify=False)
        if r.status_code == 200:
            return r.json()
        else:
            print(f"Wikipedia HTTP {r.status_code} for '{animal}': {r.text[:200]}")
    except Exception as e:
        print(f"Wikipedia summary error: {e}")
    return None

def get_image_url_for_title(title: str) -> Optional[str]:
    url = "https://en.wikipedia.org/w/api.php"
    params = {
        "action": "query", "titles": title,
        "prop": "imageinfo", "iiprop": "url",
        "iiurlwidth": 1200, "format": "json",
    }
    try:
        r = SESSION.get(url, params=params, timeout=10)
        pages = r.json().get("query", {}).get("pages", {})
        for page in pages.values():
            info = page.get("imageinfo", [])
            if info:
                return info[0].get("thumburl") or info[0].get("url")
    except Exception as e:
        print(f"Image URL error: {e}")
    return None

def get_wikipedia_images(animal: str, wiki_data: dict) -> List[str]:
    images = []

    thumb = wiki_data.get("thumbnail", {}).get("source")
    if thumb:
        images.append(thumb)

    url = "https://en.wikipedia.org/w/api.php"
    params = {
        "action": "query", "titles": animal,
        "prop": "images", "imlimit": 20, "format": "json",
    }
    try:
        r = SESSION.get(url, params=params, timeout=10)
        pages = r.json().get("query", {}).get("pages", {})
        for page in pages.values():
            for img in page.get("images", []):
                if len(images) >= 2:
                    break
                title = img["title"]
                title_lower = title.lower()
                if not any(ext in title_lower for ext in [".jpg", ".jpeg", ".png"]):
                    continue
                if any(skip in title_lower for skip in [
                    "icon", "logo", "map", "flag", "range", "distribution",
                    "svg", "blank", "locator", "symbol", "coat",
                ]):
                    continue
                img_url = get_image_url_for_title(title)
                if img_url and img_url not in images:
                    images.append(img_url)
    except Exception as e:
        print(f"Wikipedia images error: {e}")

    return images[:2]

# ── Format the Telegram message ────────────────────────────────────────────────
def format_message(animal: str, wiki_data: dict) -> str:
    emoji = get_emoji(animal)
    slug = animal.replace(" ", "_")

    sentences = [s.strip() for s in wiki_data.get("extract", "").replace("\n", " ").split(". ") if s.strip()]

    hook = sentences[0] if sentences else animal
    if not hook.endswith("."):
        hook += "."

    bullets = []
    for s in sentences[1:3]:
        if not s.endswith("."):
            s += "."
        if len(s) > 200:
            s = s[:197] + "…"
        bullets.append(f"• {s}")

    return (
        f"{emoji} *{animal}*\n\n"
        f"{hook}\n\n"
        f"{chr(10).join(bullets)}\n\n"
        f"🔍 [Read more on Wikipedia](https://en.wikipedia.org/wiki/{slug})"
    )

# ── Telegram senders ───────────────────────────────────────────────────────────
def send_photo(token: str, channel: str, photo_url: str, caption: str) -> bool:
    r = SESSION.post(
        f"https://api.telegram.org/bot{token}/sendPhoto",
        data={"chat_id": channel, "photo": photo_url,
              "caption": caption, "parse_mode": "Markdown"},
        timeout=30,
    )
    if not r.ok:
        print(f"sendPhoto error: {r.text}")
    return r.ok

def send_media_group(token: str, channel: str, images: list, caption: str) -> bool:
    media = []
    for i, img_url in enumerate(images):
        item = {"type": "photo", "media": img_url}
        if i == 0:
            item["caption"] = caption
            item["parse_mode"] = "Markdown"
        media.append(item)
    r = SESSION.post(
        f"https://api.telegram.org/bot{token}/sendMediaGroup",
        data={"chat_id": channel, "media": json.dumps(media)},
        timeout=30,
    )
    if not r.ok:
        print(f"sendMediaGroup error: {r.text}")
    return r.ok

def send_text(token: str, channel: str, text: str) -> bool:
    r = SESSION.post(
        f"https://api.telegram.org/bot{token}/sendMessage",
        data={"chat_id": channel, "text": text, "parse_mode": "Markdown"},
        timeout=30,
    )
    return r.ok

# ── Main ───────────────────────────────────────────────────────────────────────
def main():
    config = load_config()
    token = config.get("bot_token", "")
    channel = config.get("channel_id", "")

    if not token or token == "YOUR_BOT_TOKEN_HERE":
        print("ERROR: Please set your bot_token in config.json")
        sys.exit(1)
    if not channel or channel == "@your_channel":
        print("ERROR: Please set your channel_id in config.json")
        sys.exit(1)

    animal = get_animal_of_the_day()
    print(f"🐾 Today's animal: {animal}")

    wiki_data = get_wikipedia_summary(animal)
    if not wiki_data:
        print(f"ERROR: No Wikipedia data for '{animal}'")
        sys.exit(1)

    images = get_wikipedia_images(animal, wiki_data)
    print(f"🖼  Images found: {len(images)}")

    message = format_message(animal, wiki_data)

    if len(images) >= 2:
        ok = send_media_group(token, channel, images, message)
    elif len(images) == 1:
        ok = send_photo(token, channel, images[0], message)
    else:
        print("⚠️  No images found — sending text only")
        ok = send_text(token, channel, message)

    if ok:
        print("✅ Post sent!")
    else:
        print("❌ Failed to send post")
        sys.exit(1)

if __name__ == "__main__":
    main()
