"""PokeLookup CLI — look up a Pokemon by name or Dex number.

Usage:
    python pokelookup.py <pokemon_name_or_id>
    python pokelookup.py <pokedex.csv> <pokemon_name_or_id>

For the graphical Pokedex, run: python pokedex_gui.py
"""

import csv
import sys
import textwrap
from pathlib import Path

if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf8"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

DEFAULT_CSV = Path(__file__).resolve().parent / "pokedex.csv"

STAT_KEYS = [
    ("HP", "HP"), ("Attack", "Attack"), ("Defense", "Defense"),
    ("SpAttack", "Sp. Atk"), ("SpDefense", "Sp. Def"), ("Speed", "Speed"),
]


def load_pokemon_data(file_name):
    pokemon_data = {}
    id_to_name = {}
    with open(file_name, encoding="utf-8") as file:
        for row in csv.DictReader(file):
            pokemon_data[row["Name"].lower()] = row
            id_to_name[row["ID"]] = row["Name"]
    return pokemon_data, id_to_name


def get_evolution_name(evolution_ids, id_to_name):
    names = [
        id_to_name[eid.strip()]
        for eid in evolution_ids.split(",")
        if eid.strip() in id_to_name
    ]
    return ", ".join(names) if names else "None"


def stat_bar(value, width=20):
    filled = round(int(value) / 255 * width)
    return "█" * filled + "░" * (width - filled)


def print_pokemon(pokemon, id_to_name):
    genus = f"  —  {pokemon['Genus']}" if pokemon.get("Genus") else ""
    print(f"#{pokemon['ID']}  {pokemon['Name']}{genus}")
    if pokemon.get("Bio"):
        print(textwrap.fill(pokemon["Bio"], 68, initial_indent="  ",
                            subsequent_indent="  "))
    print(f"  Types:      {pokemon['Types']}")
    print(f"  Weaknesses: {pokemon['Weaknesses']}")
    print(f"  Evolution:  {get_evolution_name(pokemon['Evolution'], id_to_name)}")
    if pokemon.get("HeightM"):
        print(f"  Height:     {pokemon['HeightM']} m")
        print(f"  Weight:     {pokemon['WeightKg']} kg")
    if pokemon.get("Generation"):
        print(f"  First seen: {pokemon['Generation']} — {pokemon['Region']}")
        print(f"  Location:   {pokemon['FirstLocation']}")
    if pokemon.get("HP"):
        print("  Base stats:")
        total = 0
        for key, label in STAT_KEYS:
            value = pokemon[key]
            total += int(value)
            print(f"    {label:<8} {value:>3}  {stat_bar(value)}")
        print(f"    {'Total':<8} {total:>3}")
    if pokemon.get("Fact"):
        print(textwrap.fill(f"★ {pokemon['Fact']}", 68, initial_indent="  ",
                            subsequent_indent="    "))


def main():
    args = sys.argv[1:]
    if len(args) == 1:
        file_name, query = DEFAULT_CSV, args[0]
    elif len(args) == 2:
        file_name, query = args
    else:
        print("Usage: python pokelookup.py [pokedex.csv] <pokemon_name_or_id>")
        sys.exit(1)

    pokemon_data, id_to_name = load_pokemon_data(file_name)

    query = query.lower()
    if query.isdigit():
        query_name = id_to_name.get(f"{int(query):03d}", "").lower()
        query = query_name or query

    if query in pokemon_data:
        print_pokemon(pokemon_data[query], id_to_name)
    else:
        matches = [name for name in pokemon_data if name.startswith(query)]
        if len(matches) == 1:
            print_pokemon(pokemon_data[matches[0]], id_to_name)
        elif matches:
            names = ", ".join(pokemon_data[m]["Name"] for m in sorted(matches))
            print(f"Did you mean: {names}?")
        else:
            print("Pokémon not found.")
            sys.exit(1)


if __name__ == "__main__":
    main()
