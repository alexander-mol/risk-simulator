import pandas as pd
import networkx as nx
import matplotlib.pyplot as plt
from root_path import ROOT_PATH


# df = pd.read_excel("standard_map_data.xlsx")
territory_attributes = pd.read_excel(f"{ROOT_PATH}/maps/standard_map_data.xlsx", sheet_name=0).\
    set_index("territory").to_dict('index')
adjacency = pd.read_excel(f"{ROOT_PATH}/maps/standard_map_data.xlsx", sheet_name=1)

g = nx.Graph()
for i, row in adjacency.iterrows():
    for j in range(len(row)):
        if row[j] == 1:
            g.add_edge(adjacency.columns[i+1], adjacency.columns[j])

nx.set_node_attributes(g, territory_attributes)

continents = {}
for t in territory_attributes:
    continents.setdefault(territory_attributes[t]["continent"], []).append(t)


def render(g, ply):
    color_map = {
        "A": "deepskyblue",
        "B": "red",
        "C": "yellow",
        "D": "green",
    }
    colors = [color_map[g.nodes[n]["nation"]] for n in g.nodes]
    troops = {n: g.nodes[n]["troops"] for n in g.nodes}

    plt.figure(ply)

    plt.imshow(plt.imread(f"{ROOT_PATH}/maps/map.png"), alpha=0.75)

    nx.draw_networkx(g, pos={n: (g.nodes[n]["x"]*58 + 120, 490 - g.nodes[n]["y"]*59) for n in g.nodes}, node_color=colors, labels=troops, edgelist=[], node_size=100, font_size=8)

    plt.text(10, 20, f"Ply: {ply}", fontsize=8)
    # plt.show()


map_info = {
    "graph": g,
    "nations": ["A", "B", "C", "D"],
    "continent_bonuses": {
        "North America": 5, "South America": 2, "Africa": 3, "Europe": 5, "Asia": 7, "Oceania": 2
    },
    "continent_definition": continents,
    "renderer": render,
}


if __name__ == "__main__":
    render(g, 0)
