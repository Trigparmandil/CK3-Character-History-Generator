import os
import re
import graphviz
from collections import defaultdict
from config_loader import ConfigLoader

#########################################################
#   For the graph direction, valid arguments are:       #
#   LR - Left->Right                                    #
#   RL - Right->Left                                    #
#   TB - Top->Bottom                                    #
#   BT - Bottom->Top                                    #
#   Both - Will generate LR and TB both                 #
#########################################################


class FamilyTree:
    def __init__(self, character_file, title_file, config):
        self.characters = {}
        self.dynasties = defaultdict(list)  # Stores characters by dynasty
        self.title_holders = {}  # Store characters who inherited the title
        self.load_characters(character_file)
        self.load_titles(title_file)
        self.graphs = {}  # Stores Graphviz objects for each dynasty
        self.config = config
        self.graphLook = self.config['initialization']['treeGeneration']

    def load_characters(self, filename):
        """Parse the .txt file to extract character details."""
        with open(filename, "r", encoding="utf-8") as f:  # Ensure UTF-8 encoding
            data = f.read()

        def convert_to_ingame_date(year):
            """Convert the year into T.A. or S.A. format."""
            if year.isdigit():  # Ensure it's a valid number
                year = int(year)
                if year > 4033:
                    return f"{year - 4033}"
                elif 592 < year <= 4033:
                    return f"{year - 592}"
            return ""  # Default if invalid

        # Regex to find each character block
        character_blocks = re.findall(r"(\w+) = \{\s*((?:[^{}]*|\{(?:[^{}]*|\{[^}]*\})*\})*)\s*\}", data, re.DOTALL)

        for identifier, content in character_blocks:
            char_data = {"id": identifier}

            # Extracting values
            char_data["name"] = self.extract_value(r"name\s*=\s*(\w+)", content)
            char_data["father"] = self.extract_value(r"father\s*=\s*(\w+)", content, default=None)
            char_data["mother"] = self.extract_value(r"mother\s*=\s*(\w+)", content, default=None)
            char_data["dynasty"] = self.extract_value(r"dynasty\s*=\s*(\w+)", content, default="Lowborn")

            # Ensure "is_female" is detected correctly
            is_female_match = re.search(r"\bfemale\b\s*=\s*yes", content, re.IGNORECASE)
            char_data["female"] = "yes" if is_female_match else "no"  # Default to male if absent

            # Check for bastard trait
            is_bastard_match = re.search(r"\btrait\s*=\s*bastard\b", content, re.IGNORECASE)
            char_data["is_bastard"] = True if is_bastard_match else False  # Flag for bastard trait

            # Debugging output
            # print(f"Is Female: {is_female_match}, Is Bastard: {char_data['is_bastard']}")

            # Extract birth and death years
            birth_match = re.search(r"(\d{4})\.\d{2}\.\d{2}\s*=\s*\{\s*birth\s*=\s*yes", content)
            death_match = re.search(r"(\d{4})\.\d{2}\.\d{2}\s*=\s*\{\s*death", content, re.DOTALL)

            char_data["birth_year"] = convert_to_ingame_date(birth_match.group(1)) if birth_match else ""
            char_data["death_year"] = convert_to_ingame_date(death_match.group(1)) if death_match else ""

            # Store character data
            self.characters[identifier] = char_data
            self.dynasties[char_data["dynasty"]].append(identifier)  # Group by dynasty

        # Debugging Output: Ensure Characters Are Loaded
        # print("Characters Loaded:", list(self.characters.keys()))  # <-- Debugging line

    def load_titles(self, filename):
        """Parse title history to find characters who held a title and track their ruling dates."""
        try:
            with open(filename, "r", encoding="utf-8") as f:
                data = f.read()
        except FileNotFoundError:
            print(f"Warning: {filename} not found. Skipping title processing.")
            return

        title_blocks = re.findall(r"(\w+)\s*=\s*\{([^{}]*(?:\{[^{}]*\}[^{}]*)*)\}", data, re.DOTALL)

        for title_name, content in title_blocks:
            matches = re.findall(r"(\d{4}\.\d{2}\.\d{2})\s*=\s*\{[^}]*\bholder\s*=\s*(\w+)", content)
            
            previous_holder = None
            previous_date = None
            
            for date, holder in matches:
                # Convert the date string into a comparable format (just year, month, day)
                date_parts = date.split('.')
                year = int(date_parts[0])
                month = int(date_parts[1])
                day = int(date_parts[2])
                
                # If we have a previous holder, mark the previous holder's end date
                if previous_holder and previous_holder != holder:
                    if previous_holder != "0":  # Ignore empty holder
                        self.title_holders[previous_holder]["end_date"] = f"{year}.{month:02d}.{day:02d}"
                
                # Add current holder with their start date
                if holder != "0":  # Ignore cases where no one inherits
                    if holder not in self.title_holders:
                        self.title_holders[holder] = {"start_date": f"{year}.{month:02d}.{day:02d}", "end_date": None}
                    else:
                        self.title_holders[holder]["start_date"] = f"{year}.{month:02d}.{day:02d}"
                
                # Update the previous holder and previous date for the next iteration
                previous_holder = holder
                previous_date = f"{year}.{month:02d}.{day:02d}"

            # Check if any holder doesn't have an end date (i.e., they were the last holder)
            if previous_holder and previous_holder != "0" and self.title_holders[previous_holder]["end_date"] is None:
                self.title_holders[previous_holder]["end_date"] = "Present"  # Or any appropriate term for ongoing reign

        # Debug print to check the data
        # print("Title Holders with Start and End Dates:", self.title_holders)

    def extract_value(self, pattern, text, default=""):
        """Helper function to extract values from a text block."""
        match = re.search(pattern, text)
        return match.group(1) if match else default

    def build_trees(self):
        """Generate a family tree visualization for each dynasty."""
        for dynasty, members in self.dynasties.items():
            graph = graphviz.Digraph(comment=f"{dynasty} Family Tree", graph_attr={"rankdir": self.graphLook, "bgcolor": "#A0C878"})

            def convert_to_ingame_date(year):
                """Convert the year into T.A. or S.A. format."""
                if year.isdigit():  # Ensure it's a valid number
                    year = int(year)
                    if year > 4033:
                        return f"{year - 4033}"
                    elif 592 < year <= 4033:
                        return f"{year - 592}"
                return ""  # Default if invalid

            # Categorize members into males, females, and rulers
            male_count = sum(1 for char_id in members if self.characters[char_id].get("female") != "yes")
            female_count = sum(1 for char_id in members if self.characters[char_id].get("female") == "yes")
            ruler_count = sum(1 for char_id in members if char_id in self.title_holders)

            # Find the oldest and youngest birth years
            birth_years = [self.characters[char_id]["birth_year"] for char_id in members]
            oldest_birth_year = min(birth_years)
            youngest_birth_year = max(birth_years)

            # Convert birth years to in-game format
            oldest_in_game_year = convert_to_ingame_date(str(oldest_birth_year))
            youngest_in_game_year = convert_to_ingame_date(str(youngest_birth_year))

            # Create a label with the counts for males, females, rulers, and the span of the dynasty
            count_label = (f"Total Members: {len(members)}\n"
                        f"Males: {male_count}\nFemales: {female_count}\nRulers: {ruler_count}\n")

            # Add a node for displaying the counts in the top-left corner
            graph.node("dynasty_count", label=count_label, shape="plaintext", width="0", height="0", style="solid", color="transparent", fontcolor="black")

            # Keep track of external parent nodes and marriages
            external_nodes = {}
            marriages = {}  # Dictionary to store marriage relationships (spouse1 -> spouse2)

            # Sort characters by birth year to ensure eldest is at the top
            sorted_members = sorted(members, key=lambda char_id: self.characters[char_id]["birth_year"])

            for char_id in sorted_members:
                char = self.characters[char_id]
                
                # Check if the character inherited a title
                node_color = "pink" if char_id in self.title_holders else "white"

                # Format the label with proper line breaks
                birth_date = char["birth_year"]
                death_date = char["death_year"]
                start_date = self.title_holders.get(char_id, {}).get("start_date", "N/A")
                end_date = self.title_holders.get(char_id, {}).get("end_date", "N/A")
                
                # Convert the start and end dates to in-game year format
                start_year = convert_to_ingame_date(start_date.split('.')[0] if start_date != "N/A" else "N/A")
                end_year = convert_to_ingame_date(end_date.split('.')[0] if end_date != "N/A" else "N/A")

                # Build the label, only include "Ruled: start_year - end_year" if the character has ruled
                ruled_label = ""
                
                # Check if both start_year and end_year are valid and not "N/A"
                if start_year and start_year != "N/A" and end_year and end_year != "N/A":
                    ruled_label = f" Ruled: {start_year} - {end_year}"

                label = f'< <b>{char["name"]}</b><br/>{char["id"]}<br/>{birth_date} - {death_date}<br/>{ruled_label} >'

                border_color = "blue"  # Default for males
                if char.get("female") == "yes":
                    border_color = "red"  # Assign red for females

                # Check if the character is a bastard and add a diagonal mark
                node_style = "filled"
                fillcolor = node_color
                penwidth = "5"
                diagonal_mark = ""

                if char.get("is_bastard", False):  # Check if the character is a bastard
                    diagonal_mark = 'diagonal line from top-left to bottom-right'
                    # To represent the mark, we'll use a "diagonal line" as an additional part of the node
                    node_style += ", diagonals"  # We use a custom style to simulate diagonal lines

                # Create the node with a large enough diagonal mark for bastards
                graph.node(char["id"], label=label, style=node_style, fillcolor=fillcolor, color=border_color, penwidth=penwidth)

                # Check for a spouse (marriage detection)
                spouse_id = self.characters.get(char_id, {}).get("spouse")  # Assuming 'spouse' field exists
                if spouse_id:
                    marriages[char_id] = spouse_id
                    marriages[spouse_id] = char_id  # Ensure bidirectional marriage

                # Draw edges for parents
                for parent_type in ["father", "mother"]:
                    parent_id = char.get(parent_type)
                    if parent_id in self.characters:
                        parent_dynasty = self.characters[parent_id]["dynasty"]

                        # If parent is in the same dynasty, link directly
                        if parent_dynasty == dynasty:
                            graph.edge(parent_id, char_id)

                        # Else, check if we should show external parents
                        elif self.config.get('initialization', {}).get('spouseVisible', []) == "yes":
                            external_node_id = f"external_{parent_id}"
                            if external_node_id not in external_nodes:
                                external_label = (
                                    f'< <b>{self.characters[parent_id]["name"]}</b><br/>' 
                                    f'{self.characters[parent_id]["birth_year"]} - '
                                    f'{self.characters[parent_id]["death_year"]} >'
                                )
                                graph.node(external_node_id, label=external_label,
                                        shape="ellipse", style="dashed")
                                external_nodes[external_node_id] = external_label

                            # Draw dashed edge from external parent to child
                            graph.edge(external_node_id, char_id, style="dashed")

                            # Check for spouse of external parent and draw a thick line if exists
                            spouse_id = self.characters.get(parent_id, {}).get("spouse")
                            if spouse_id and spouse_id in self.characters:
                                graph.edge(external_node_id, spouse_id,
                                        style="bold", penwidth="3", color="black")

            # Draw marriage lines with bold, thick edges
            for spouse1, spouse2 in marriages.items():
                if spouse1 in self.characters and spouse2 in self.characters:
                    # Connect spouses with a bold line
                    graph.edge(spouse1, spouse2, style="bold", penwidth="3", color="black")

                    # Use a subgraph to position spouses next to each other
                    with graph.subgraph() as s:
                        s.attr(rankdir=self.graphLook, rank='same')
                        s.node(spouse1)
                        s.node(spouse2)
                        s.edge(spouse1, spouse2, style="bold", penwidth="3", color="black")

            self.graphs[dynasty] = graph  # Store graph for later rendering

    def render_trees(self):
        """Render the family trees to files in 'Dynasty Preview' folder."""
        output_folder = "Dynasty Preview"
        os.makedirs(output_folder, exist_ok=True)  # Create the folder if it doesn't exist

        for dynasty, graph in self.graphs.items():
            filename = os.path.join(output_folder, f"family_tree_{dynasty}")
            graph.render(filename, format="png", cleanup=True)
            print(f"Family tree for {dynasty} saved as {filename}.png")

if __name__ == "__main__":
    config_loader = ConfigLoader('config')  # Ensure 'config' directory is correct
    tree = FamilyTree("family_history.txt", "title_history.txt", config_loader.config)  # Ensure both files exist
    tree.build_trees()
    tree.render_trees()