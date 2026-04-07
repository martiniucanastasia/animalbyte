#!/usr/bin/env python3
"""
Utility: rebuild animals.json from iNaturalist.
Keeps only animals confirmed to have research-grade sound observations.
Also discovers new popular animals with sounds.

Usage:
  python3 update_animals.py           # validate + enrich current list
  python3 update_animals.py --fresh   # ignore current list, build from scratch
"""

import json
import sys
import time
from pathlib import Path
from typing import Optional

import requests
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

SESSION = requests.Session()
SESSION.verify = False
SESSION.headers.update({"User-Agent": "AnimalFactsBot/1.0"})

ANIMALS_FILE = Path(__file__).parent / "animals.json"

ICONIC_TAXA = [
    "Mammalia", "Aves", "Reptilia", "Amphibia",
    "Actinopterygii", "Insecta", "Arachnida", "Mollusca",
]
PREFERRED_RANKS = {"species", "subspecies", "hybrid", "variety", "genus"}


def has_sound(taxon_id: int) -> bool:
    r = SESSION.get(
        "https://api.inaturalist.org/v1/observations",
        params={"taxon_id": taxon_id, "sounds": "true",
                "quality_grade": "research", "per_page": 1},
        timeout=10,
    )
    if r.status_code != 200:
        return False
    return r.json().get("total_results", 0) > 0


def resolve_taxon(name: str) -> Optional[dict]:
    """Return best-matching animal taxon for a common name."""
    r = SESSION.get(
        "https://api.inaturalist.org/v1/taxa",
        params={"q": name, "locale": "en", "taxon_id": 1,
                "photos": "true", "per_page": 10, "order_by": "observations_count"},
        timeout=10,
    )
    if r.status_code != 200:
        return None
    results = r.json().get("results", [])
    ranked = [t for t in results if t.get("rank") in PREFERRED_RANKS]
    for taxon in (ranked or results):
        if taxon.get("iconic_taxon_name") in {*ICONIC_TAXA, "Animalia"}:
            return taxon
    return None


def fetch_popular_with_sounds(per_iconic: int = 50) -> list:
    """Pull top observed species with sounds from iNaturalist across all animal groups."""
    names = []
    for iconic in ICONIC_TAXA:
        print(f"  Fetching top {iconic} with sounds...")
        r = SESSION.get(
            "https://api.inaturalist.org/v1/observations/species_counts",
            params={"sounds": "true", "quality_grade": "research",
                    "iconic_taxa": iconic, "per_page": per_iconic},
            timeout=15,
        )
        if r.status_code != 200:
            print(f"  HTTP {r.status_code} for {iconic}, skipping")
            continue
        for entry in r.json().get("results", []):
            taxon = entry.get("taxon", {})
            name = taxon.get("preferred_common_name") or taxon.get("name")
            if name and name not in names:
                names.append(name)
        time.sleep(0.5)
    return names


def main():
    fresh = "--fresh" in sys.argv

    if fresh:
        print("🌍 Fresh mode — fetching popular animals with sounds from iNaturalist...")
        candidates = fetch_popular_with_sounds(per_iconic=100)
        print(f"   Found {len(candidates)} candidates")
    else:
        if not ANIMALS_FILE.exists():
            print("ERROR: animals.json not found. Run with --fresh to build from scratch.")
            sys.exit(1)
        with open(ANIMALS_FILE) as f:
            candidates = json.load(f)
        print(f"📋 Validating {len(candidates)} animals from current animals.json...")

    confirmed = []
    skipped = []
    limit = 150

    for i, name in enumerate(candidates, 1):
        if len(confirmed) >= limit:
            print(f"\n🎯 Reached {limit} confirmed animals — stopping early.")
            break
        print(f"[{i}/{len(candidates)}] {name} ...", end=" ", flush=True)
        taxon = resolve_taxon(name)
        if not taxon:
            print("✗ not found on iNaturalist")
            skipped.append(name)
            time.sleep(0.3)
            continue
        if has_sound(taxon["id"]):
            label = taxon.get("preferred_common_name") or name
            if label not in confirmed:
                confirmed.append(label)
            print(f"✓  ({label})")
        else:
            print("✗ no sound")
            skipped.append(name)
        time.sleep(0.3)   # be polite to the API

    with open(ANIMALS_FILE, "w") as f:
        json.dump(confirmed, f, ensure_ascii=False, indent=2)

    print(f"\n✅ Done! {len(confirmed)} animals with sounds saved to animals.json")
    if skipped:
        print(f"🗑  Removed ({len(skipped)} without sounds): {', '.join(skipped)}")


if __name__ == "__main__":
    main()
