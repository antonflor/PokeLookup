# PokeLookup

## Description

PokeLookup is a Pokédex for the terminal and the desktop. It covers 898 Pokémon
(Kanto through Galar) and shows types, weaknesses, evolutions, base stats,
height/weight, and where each Pokémon first appeared — both the game/region it
debuted in and its earliest wild encounter location.

## Features

- **Pokédex-inspired GUI** (`pokedex_gui.py`) — classic red-shell design with
  live search, official sprites, colored type badges, base-stat bars, and a
  clickable evolution chain. Pure tkinter, no packages to install.
- **Command-line lookup** (`pokelookup.py`) — search by name, name prefix, or
  Dex number; prints stats with text bars.
- **Rich data** — base stats (HP / Attack / Defense / Sp. Atk / Sp. Def /
  Speed), height, weight, generation, region, and first-appearance location
  for every Pokémon, sourced from [PokéAPI](https://pokeapi.co/) open data.
- **Bios and fun facts** — every Pokémon has its genus ("Seed Pokémon"), an
  official Pokédex bio, and a cool fact: a data-derived superlative where one
  exists ("highest base Defense of all 898 Pokémon", "the only Ghost/Dragon
  type") or its classic original Pokédex entry otherwise.

## Installation

```
git clone git@github.com:antonflor/PokeLookup.git
```

Requires Python 3 (tkinter is included in the standard Windows/macOS installers).

## Usage

### GUI

```
python pokedex_gui.py
```

Type in the search box to filter by name or Dex number. Click a Pokémon to see
its details; click an evolution badge to jump to that Pokémon. Sprites are
downloaded once from the PokéAPI sprites repository and cached in `sprites/`
(without internet you get a Poké Ball placeholder instead).

### Command line

```
python pokelookup.py pikachu        # by name
python pokelookup.py 150            # by Dex number
python pokelookup.py char           # prefix search suggests matches
python pokelookup.py my.csv mew     # explicit CSV path (legacy form)
```

## Data

`pokedex.csv` holds all Pokémon data. To rebuild the stats/appearance columns
from the latest PokéAPI data files:

```
python scripts/enrich_pokedex.py
```

The script keeps the existing Pokémon list, types, weaknesses, and evolution
columns and refreshes everything else.
