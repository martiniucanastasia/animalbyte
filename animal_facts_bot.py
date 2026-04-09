#!/usr/bin/env python3
"""
Daily Animal Facts Telegram Bot
Posts an interesting animal fact with photos and sound to a Telegram channel.
All data sourced from iNaturalist.
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
POSTED_FILE = Path(__file__).parent / "posted.json"

def load_posted() -> set:
    if POSTED_FILE.exists():
        with open(POSTED_FILE) as f:
            return set(json.load(f))
    return set()

def save_posted(posted: set):
    with open(POSTED_FILE, "w") as f:
        json.dump(sorted(posted), f, ensure_ascii=False, indent=2)

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

# ── Animal list (loaded from animals.json) ────────────────────────────────────
ANIMALS_FILE = Path(__file__).parent / "animals.json"

def load_animals() -> list:
    if not ANIMALS_FILE.exists():
        print("ERROR: animals.json not found")
        sys.exit(1)
    with open(ANIMALS_FILE) as f:
        return json.load(f)

ANIMALS = load_animals()

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
def get_day_index() -> int:
    day = datetime.now().timetuple().tm_yday
    year = datetime.now().year
    return (day + year * 100) % len(ANIMALS)

def find_animal_with_sound(candidates: list) -> Optional[tuple]:
    """Try candidates in order; return (animal, inat_data, sound) for the first with a sound."""
    for animal in candidates:
        print(f"🔍 Trying: {animal}")
        inat_data = get_inaturalist_data(animal)
        if not inat_data:
            continue
        sound = get_inaturalist_sound(inat_data["id"])
        if sound:
            return animal, inat_data, sound
        print(f"   No sound for {animal}, skipping")
    return None

# ── iNaturalist ────────────────────────────────────────────────────────────────
ANIMAL_ICONIC_TAXA = {
    "Mammalia", "Aves", "Reptilia", "Amphibia",
    "Actinopterygii", "Insecta", "Arachnida", "Mollusca", "Animalia",
}

def get_inaturalist_data(animal: str) -> Optional[dict]:
    """Fetch taxon name, description, and photos from iNaturalist."""
    url = "https://api.inaturalist.org/v1/taxa"
    params = {
        "q": animal,
        "locale": "ru",
        "taxon_id": 1,        # Animalia kingdom — no plants or fungi
        "photos": "true",
        "per_page": 10,
        "order_by": "observations_count",
    }
    try:
        r = SESSION.get(url, params=params, timeout=10)
        if r.status_code != 200:
            print(f"iNaturalist taxa HTTP {r.status_code}")
            return None
        # Prefer species/genus over family/order/class
        PREFERRED_RANKS = {"species", "subspecies", "hybrid", "variety", "genus"}
        results = r.json().get("results", [])
        ranked = [t for t in results if t.get("rank") in PREFERRED_RANKS]
        candidates = ranked if ranked else results

        for taxon in candidates:
            iconic = taxon.get("iconic_taxon_name")
            if iconic and iconic not in ANIMAL_ICONIC_TAXA:
                print(f"Skipping non-animal: {taxon.get('name')} ({iconic})")
                continue
            if not taxon.get("default_photo"):
                continue

            # Collect up to 3 large photos
            images = []
            for tp in taxon.get("taxon_photos", [])[:6]:
                raw = tp.get("photo", {}).get("url", "")
                if raw:
                    large = raw.replace("/square.", "/large.").replace("square", "large")
                    if large not in images:
                        images.append(large)
                if len(images) >= 3:
                    break
            if not images:
                raw = taxon["default_photo"]["url"]
                images.append(raw.replace("/square.", "/large.").replace("square", "large"))

            common_name = taxon.get("preferred_common_name") or animal
            scientific_name = taxon.get("name", "")
            description = taxon.get("wikipedia_summary", "")
            taxon_id = taxon["id"]

            # If fewer than 3 photos, fill from research-grade observations
            if len(images) < 3:
                try:
                    obs_r = SESSION.get(
                        "https://api.inaturalist.org/v1/observations",
                        params={"taxon_id": taxon_id, "quality_grade": "research",
                                "photos": "true", "per_page": 15, "order_by": "votes"},
                        timeout=10,
                    )
                    if obs_r.status_code == 200:
                        for obs in obs_r.json().get("results", []):
                            for photo in obs.get("photos", []):
                                raw = photo.get("url", "")
                                if raw:
                                    large = raw.replace("/square.", "/large.").replace("square", "large")
                                    if large not in images:
                                        images.append(large)
                                if len(images) >= 3:
                                    break
                            if len(images) >= 3:
                                break
                except Exception as e:
                    print(f"Observation photos error: {e}")

            images = images[:3]
            print(f"iNaturalist taxon: {common_name} ({scientific_name}) id={taxon_id}")
            print(f"iNaturalist images: {len(images)}")

            return {
                "id": taxon_id,
                "common_name": common_name,
                "scientific_name": scientific_name,
                "description": description,
                "images": images,
                "inat_url": f"https://www.inaturalist.org/taxa/{taxon_id}",
            }
    except Exception as e:
        print(f"iNaturalist data error: {e}")
    return None


def get_inaturalist_sound(taxon_id: int) -> Optional[tuple]:
    """Return (file_url, content_type) for the best sound observation of this taxon."""
    url = "https://api.inaturalist.org/v1/observations"
    params = {
        "taxon_id": taxon_id,
        "sounds": "true",
        "quality_grade": "research",
        "per_page": 10,
        "order_by": "votes",
    }
    try:
        r = SESSION.get(url, params=params, timeout=10)
        if r.status_code != 200:
            return None
        for obs in r.json().get("results", []):
            for sound in obs.get("sounds", []):
                file_url = sound.get("file_url")
                content_type = sound.get("file_content_type", "audio/mpeg")
                if file_url:
                    print(f"iNaturalist sound: {file_url} ({content_type})")
                    return file_url, content_type
    except Exception as e:
        print(f"iNaturalist sound error: {e}")
    return None

# ── Format the Telegram message ────────────────────────────────────────────────
def format_message(animal: str, inat_data: dict) -> str:
    emoji = get_emoji(animal)
    common_name = inat_data["common_name"]
    scientific_name = inat_data["scientific_name"]
    inat_url = inat_data["inat_url"]

    title = f"{common_name} - {scientific_name}" if scientific_name else common_name

    return (
        f"{emoji} *{title}*\n\n"
        f"Как это животное звучит ↓"
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
    # Download images locally first — iNaturalist CDN blocks Telegram's fetch
    files = {}
    media = []
    for i, img_url in enumerate(images):
        key = f"photo{i}"
        try:
            img_r = SESSION.get(img_url, timeout=15)
            img_r.raise_for_status()
            content_type = img_r.headers.get("Content-Type", "image/jpeg")
            ext = content_type.split("/")[-1].split(";")[0] or "jpg"
            files[key] = (f"{key}.{ext}", img_r.content, content_type)
            item = {"type": "photo", "media": f"attach://{key}"}
        except Exception as e:
            print(f"Failed to download image {i} ({img_url}): {e}")
            item = {"type": "photo", "media": img_url}  # fallback to URL
        if i == 0:
            item["caption"] = caption
            item["parse_mode"] = "Markdown"
        media.append(item)
    r = SESSION.post(
        f"https://api.telegram.org/bot{token}/sendMediaGroup",
        data={"chat_id": channel, "media": json.dumps(media)},
        files=files if files else None,
        timeout=60,
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

def send_audio(token: str, channel: str, audio_url: str, title: str, content_type: str) -> bool:
    try:
        audio_r = SESSION.get(audio_url, timeout=30)
        if not audio_r.ok:
            print(f"Failed to download audio: {audio_r.status_code}")
            return False
        ext = "mp3" if "mpeg" in content_type else content_type.split("/")[-1]
        r = SESSION.post(
            f"https://api.telegram.org/bot{token}/sendAudio",
            data={"chat_id": channel, "title": f"{title} — звук", "performer": "iNaturalist"},
            files={"audio": (f"sound.{ext}", audio_r.content, content_type)},
            timeout=60,
        )
        if not r.ok:
            print(f"sendAudio error: {r.text}")
        return r.ok
    except Exception as e:
        print(f"sendAudio error: {e}")
        return False

# ── Main ───────────────────────────────────────────────────────────────────────
def main():
    import random

    config = load_config()
    token = config.get("bot_token", "")
    channel = config.get("channel_id", "")

    if not token or token == "YOUR_BOT_TOKEN_HERE":
        print("ERROR: Please set your bot_token in config.json")
        sys.exit(1)
    if not channel or channel == "@your_channel":
        print("ERROR: Please set your channel_id in config.json")
        sys.exit(1)

    args = sys.argv[1:]
    posted = load_posted()
    remaining = [a for a in ANIMALS if a not in posted]
    if not remaining:
        print("🔄 All animals posted — resetting history")
        posted = set()
        save_posted(posted)
        remaining = ANIMALS.copy()
    print(f"📋 {len(remaining)} animals remaining (of {len(ANIMALS)} total)")

    if "--random" in args:
        print("🎲 Random mode — searching for an animal with sound...")
        candidates = remaining.copy()
        random.shuffle(candidates)
        result = find_animal_with_sound(candidates)

    elif args:
        # Specific animal requested
        animal = " ".join(a for a in args if not a.startswith("--"))
        print(f"🐾 Requested animal: {animal}")
        inat_data = get_inaturalist_data(animal)
        if not inat_data:
            print(f"ERROR: No iNaturalist data for '{animal}'")
            sys.exit(1)
        sound = get_inaturalist_sound(inat_data["id"])
        if not sound:
            print(f"ERROR: No sound found for '{animal}' on iNaturalist")
            sys.exit(1)
        result = (animal, inat_data, sound)

    else:
        # Daily mode — pick from remaining, prefer today's slot order
        print("📅 Daily mode — finding today's animal with sound...")
        start = get_day_index() % len(remaining)
        candidates = [remaining[(start + i) % len(remaining)] for i in range(len(remaining))]
        result = find_animal_with_sound(candidates)

    if not result:
        print("ERROR: Could not find any animal with a sound recording")
        sys.exit(1)

    animal, inat_data, sound = result
    print(f"🐾 Selected: {animal} ({inat_data['common_name']})")

    images = inat_data["images"]
    print(f"🖼  Images found: {len(images)}")

    message = format_message(animal, inat_data)

    if len(images) >= 2:
        ok = send_media_group(token, channel, images[:3], message)
    elif len(images) == 1:
        ok = send_photo(token, channel, images[0], message)
    else:
        print("⚠️  No images — sending text only")
        ok = send_text(token, channel, message)

    if not ok:
        print("❌ Failed to send post")
        sys.exit(1)

    print("✅ Post sent!")
    posted.add(animal)
    save_posted(posted)
    print(f"📝 Saved '{animal}' to posted history ({len(posted)}/{len(ANIMALS)})")

    audio_url, content_type = sound
    audio_ok = send_audio(token, channel, audio_url, inat_data["common_name"], content_type)
    print("🔊 Audio sent!" if audio_ok else "⚠️  Audio send failed (continuing)")

if __name__ == "__main__":
    main()
