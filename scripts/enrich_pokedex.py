"""One-time enrichment of pokedex.csv using PokeAPI's open data files.

Keeps the existing Pokemon list (IDs 1-898), Types, Weaknesses and Evolution
columns, and adds base stats, height/weight and first-appearance info.
Also repairs duplicate/misnumbered rows by validating names against the
official species list for each Dex ID.

Usage: python scripts/enrich_pokedex.py
"""

import csv
import re
import sys
import unicodedata
import urllib.request
from collections import defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
POKEDEX = REPO / "pokedex.csv"
BASE = "https://raw.githubusercontent.com/PokeAPI/pokeapi/master/data/v2/csv/"

FILES = [
    "pokemon.csv",            # id, identifier, species_id, height, weight
    "pokemon_stats.csv",      # pokemon_id, stat_id, base_stat
    "pokemon_species.csv",    # id, identifier, generation_id
    "encounters.csv",         # id, version_id, location_area_id, pokemon_id
    "location_areas.csv",     # id, location_id
    "location_names.csv",     # location_id, local_language_id, name
    "versions.csv",           # id, version_group_id, identifier
    "pokemon_species_names.csv",        # species_id, language, name, genus
    "pokemon_species_flavor_text.csv",  # species_id, version_id, language, text
]

GEN_INFO = {
    1: ("Gen I", "Kanto"),
    2: ("Gen II", "Johto"),
    3: ("Gen III", "Hoenn"),
    4: ("Gen IV", "Sinnoh"),
    5: ("Gen V", "Unova"),
    6: ("Gen VI", "Kalos"),
    7: ("Gen VII", "Alola"),
    8: ("Gen VIII", "Galar"),
}

STAT_IDS = {1: "HP", 2: "Attack", 3: "Defense", 4: "SpAttack", 5: "SpDefense", 6: "Speed"}


CACHE = REPO / "scripts" / ".cache"


def fetch(name):
    cached = CACHE / name
    if not cached.exists():
        print(f"  downloading {name} ...")
        CACHE.mkdir(exist_ok=True)
        with urllib.request.urlopen(BASE + name) as resp:
            cached.write_bytes(resp.read())
    with open(cached, encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def norm(name):
    """Normalize a display name for comparison: 'Mr. Mime' -> 'mrmime',
    'Nidoran(female sign)' -> 'nidoranf', 'farfetch'd' -> 'farfetchd'."""
    name = name.lower().replace("♀", "f").replace("♂", "m")
    name = unicodedata.normalize("NFKD", name)
    return re.sub(r"[^a-z0-9]", "", name)


def clean_flavor(text):
    """Game flavor text contains hard line breaks and form feeds."""
    text = text.replace("\x0c", " ").replace("\n", " ").replace("\r", " ")
    text = text.replace("POKéMON", "Pokémon").replace("POKEMON", "Pokémon")
    return re.sub(r"\s+", " ", text).strip()


STAT_LABELS = {
    "HP": "HP", "Attack": "Attack", "Defense": "Defense",
    "SpAttack": "Sp. Attack", "SpDefense": "Sp. Defense", "Speed": "Speed",
}


def build_facts(records):
    """Pick one data-derived 'cool fact' per Pokemon, preferring superlatives.

    records: list of dicts with ID, Name, Types, stats (ints), HeightM,
    WeightKg (floats), Total, bio, alt_flavor, genus, first_version.
    """
    combo_count = defaultdict(list)
    for r in records:
        combo_count[frozenset(r["Types"])].append(r["ID"])

    def leaders(keys, items):
        out = {}
        for key in keys:
            best = max(v[key] for v in items)
            out[key] = (best, [v["ID"] for v in items if v[key] == best])
        return out

    stat_keys = list(STAT_LABELS) + ["Total"]
    overall = leaders(stat_keys + ["HeightM", "WeightKg"], records)
    lightest = min(r["WeightKg"] for r in records)
    smallest = min(r["HeightM"] for r in records)
    by_type = defaultdict(list)
    for r in records:
        for t in r["Types"]:
            by_type[t].append(r)
    per_type = {t: leaders(stat_keys, members) for t, members in by_type.items()}

    facts = {}
    for r in records:
        pid = r["ID"]
        fact = None
        combo = combo_count[frozenset(r["Types"])]
        if len(r["Types"]) == 2 and len(combo) == 1:
            fact = f"The only {'/'.join(r['Types'])} type in the entire Pokédex."
        if not fact:
            for key in stat_keys:
                best, holders = overall[key]
                label = STAT_LABELS.get(key, "total base stats")
                if pid in holders:
                    who = "Has the" if len(holders) == 1 else "Tied for the"
                    fact = f"{who} highest base {label} ({best}) of all {len(records)} Pokémon."
                    break
        if not fact and pid in overall["WeightKg"][1]:
            fact = f"The heaviest Pokémon in the Pokédex at {r['WeightKg']:g} kg."
        if not fact and pid in overall["HeightM"][1]:
            fact = f"The tallest Pokémon in the Pokédex at {r['HeightM']:g} m."
        if not fact and r["WeightKg"] == lightest:
            fact = f"Tied for the lightest Pokémon in the Pokédex at {r['WeightKg']:g} kg."
        if not fact and r["HeightM"] == smallest:
            fact = f"Tied for the smallest Pokémon in the Pokédex at {r['HeightM']:g} m."
        if not fact:
            for t in r["Types"]:
                if len(by_type[t]) < 10:
                    continue
                for key in stat_keys:
                    best, holders = per_type[t][key]
                    if holders == [pid]:
                        label = STAT_LABELS.get(key, "total base stats")
                        fact = (
                            f"Has the highest base {label} ({best}) "
                            f"of all {len(by_type[t])} {t}-type Pokémon."
                        )
                        break
                if fact:
                    break
        if not fact and r["alt_flavor"]:
            fact = r["alt_flavor"]
        if not fact and r["genus"]:
            fact = f"Known as the {r['genus']}."
        facts[pid] = fact or ""
    return facts


def load_existing():
    """Parse the current pokedex.csv line by line, repairing unbalanced
    quotes so one bad row can't swallow its neighbours."""
    rows = []
    with open(POKEDEX, encoding="utf-8") as f:
        header = f.readline()
        for line in f:
            line = line.strip()
            if not line:
                continue
            if line.count('"') % 2 == 1:
                line += '"'
            row = next(csv.reader([line]))
            row = [c.strip() for c in row]
            if len(row) < 4 or not row[0].isdigit():
                continue
            rows.append(row)
    return rows


def main():
    print("Fetching PokeAPI data files:")
    data = {name: fetch(name) for name in FILES}

    # Official species names + generation, by dex id
    species = {}
    for r in data["pokemon_species.csv"]:
        species[int(r["id"])] = (r["identifier"], int(r["generation_id"]))

    # Height/weight from the default form (pokemon id == species id)
    physique = {}
    for r in data["pokemon.csv"]:
        pid = int(r["id"])
        if pid == int(r["species_id"]) and r["height"] and r["weight"]:
            physique[pid] = (int(r["height"]) / 10, int(r["weight"]) / 10)

    stats = defaultdict(dict)
    for r in data["pokemon_stats.csv"]:
        sid = int(r["stat_id"])
        if sid in STAT_IDS:
            stats[int(r["pokemon_id"])][STAT_IDS[sid]] = r["base_stat"]

    area_to_location = {int(r["id"]): int(r["location_id"]) for r in data["location_areas.csv"]}
    location_name = {
        int(r["location_id"]): r["name"]
        for r in data["location_names.csv"]
        if r["local_language_id"] == "9"
    }
    version_name = {
        int(r["id"]): r["identifier"].replace("-", " ").title() for r in data["versions.csv"]
    }

    genus = {
        int(r["pokemon_species_id"]): r["genus"]
        for r in data["pokemon_species_names.csv"]
        if r["local_language_id"] == "9" and r["genus"]
    }
    flavor = defaultdict(dict)  # species id -> version id -> cleaned text
    for r in data["pokemon_species_flavor_text.csv"]:
        if r["language_id"] == "9":
            flavor[int(r["species_id"])][int(r["version_id"])] = clean_flavor(
                r["flavor_text"]
            )

    # Earliest wild encounter: lowest version id, then first location seen
    first_enc = {}
    for r in data["encounters.csv"]:
        pid = int(r["pokemon_id"])
        ver = int(r["version_id"])
        area = int(r["location_area_id"])
        if pid not in first_enc or ver < first_enc[pid][0]:
            first_enc[pid] = (ver, area)

    # Pick the best row per dex id: prefer the one whose name matches the
    # official species name (repairs the shifted/duplicated block).
    existing = load_existing()
    by_id = {}
    for row in existing:
        pid = int(row[0])
        official = norm(species[pid][0]) if pid in species else None
        if pid not in by_id:
            by_id[pid] = row
        elif official and norm(row[1]) == official and norm(by_id[pid][1]) != official:
            by_id[pid] = row
    dropped = len(existing) - len(by_id)

    mismatches = [
        (pid, r[1], species[pid][0])
        for pid, r in sorted(by_id.items())
        if pid in species and norm(r[1]) != norm(species[pid][0])
    ]

    # Reverse evolution map (from the kept rows) for the fallback label
    evolves_from = {}
    for pid, row in by_id.items():
        evo = row[4] if len(row) > 4 else ""
        for target in evo.split(","):
            target = target.strip()
            if target.isdigit():
                evolves_from[int(target)] = row[1]

    header = [
        "ID", "Name", "Types", "Weaknesses", "Evolution",
        "HP", "Attack", "Defense", "SpAttack", "SpDefense", "Speed",
        "HeightM", "WeightKg", "Generation", "Region", "FirstLocation",
        "Genus", "Bio", "Fact",
    ]
    records = []
    missing_stats = []
    for pid in sorted(by_id):
        row = by_id[pid]
        types, weak = row[2], row[3]
        evo = row[4] if len(row) > 4 else ""
        evo = ",".join(p.strip() for p in evo.split(",") if p.strip().isdigit())

        st = stats.get(pid, {})
        if not st:
            missing_stats.append(pid)
        h, w = physique.get(pid, (0.0, 0.0))
        gen, region = GEN_INFO.get(species[pid][1], ("", "")) if pid in species else ("", "")

        if pid in first_enc:
            ver, area = first_enc[pid]
            loc = location_name.get(area_to_location.get(area, -1), "")
            first_loc = f"{loc} ({version_name.get(ver, '?')})" if loc else ""
        elif pid in evolves_from:
            first_loc = f"Evolves from {evolves_from[pid]}"
        else:
            first_loc = "Special encounter"

        entries = flavor.get(pid, {})
        bio = entries[max(entries)] if entries else ""
        # Oldest entry that actually differs from the bio (games often
        # recycle old Pokedex text verbatim).
        alt = next(
            (entries[v] for v in sorted(entries) if entries[v] != bio), ""
        )

        record = {
            "ID": pid, "Name": row[1], "TypesRaw": types, "WeaknessesRaw": weak,
            "Evolution": evo,
            "Types": [t.strip() for t in types.split(",") if t.strip()],
            "HeightM": h, "WeightKg": w, "Total": 0,
            "Generation": gen, "Region": region, "FirstLocation": first_loc,
            "genus": genus.get(pid, ""), "bio": bio, "alt_flavor": alt,
        }
        for key in STAT_LABELS:
            record[key] = int(st.get(key, 0))
            record["Total"] += record[key]
        records.append(record)

    facts = build_facts(records)
    out_rows = [
        [
            f"{r['ID']:03d}", r["Name"], r["TypesRaw"], r["WeaknessesRaw"], r["Evolution"],
            r["HP"], r["Attack"], r["Defense"], r["SpAttack"], r["SpDefense"], r["Speed"],
            r["HeightM"], r["WeightKg"], r["Generation"], r["Region"], r["FirstLocation"],
            r["genus"], r["bio"], facts[r["ID"]],
        ]
        for r in records
    ]

    with open(POKEDEX, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(header)
        writer.writerows(out_rows)

    print(f"\nWrote {len(out_rows)} Pokemon to {POKEDEX}")
    print(f"Removed {dropped} duplicate rows")
    if mismatches:
        print(f"Names differing from official species names ({len(mismatches)}):")
        for pid, ours, official in mismatches[:20]:
            print(f"  #{pid:03d} ours={ours!r} official={official!r}")
    if missing_stats:
        print(f"WARNING: no stats found for ids: {missing_stats}")


if __name__ == "__main__":
    sys.exit(main())
