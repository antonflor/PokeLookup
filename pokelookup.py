import csv
import sys

def load_pokemon_data(file_name):
    pokemon_data = {}
    id_to_name = {}
    with open(file_name, 'r') as file:
        reader = csv.reader(file)
        next(reader)
        for row in reader:
            if len(row) < 5:
                continue
            name = row[1].lower()
            id_to_name[row[0]] = row[1]  # Map ID to name
            pokemon_data[name] = {
                'ID': row[0],
                'Name': row[1],
                'Types': row[2],
                'Weaknesses': row[3],
                'Evolution': row[4] if row[4] else ""
            }
    return pokemon_data, id_to_name


def get_evolution_name(evolution_ids, id_to_name):
    if not evolution_ids:
        return "None"
    
    evolution_names = []
    for evolution_id in evolution_ids.split(','):
        evolution_name = id_to_name.get(evolution_id.strip(), "")
        if evolution_name:
            evolution_names.append(evolution_name)
    
    return ', '.join(evolution_names) if evolution_names else "None"


def main():
    if len(sys.argv) != 3:
        print("Usage: python pokemon-info2.py <pokedex.csv> <pokemon_name>")
        sys.exit(1)

    file_name = sys.argv[1]
    pokemon_name = sys.argv[2].lower()

    pokemon_data, id_to_name = load_pokemon_data(file_name)

    if pokemon_name in pokemon_data:
        pokemon = pokemon_data[pokemon_name]
        evolution_name = get_evolution_name(pokemon['Evolution'], id_to_name)
        print(f"ID: {pokemon['ID']}")
        print(f"Name: {pokemon['Name']}")
        print(f"Types: {pokemon['Types']}")
        print(f"Weaknesses: {pokemon['Weaknesses']}")
        print(f"Evolution: {evolution_name}")
    else:
        print("Pokémon not found.")

if __name__ == "__main__":
    main()

