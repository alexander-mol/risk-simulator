import os
import _pickle as pickle
import matplotlib.pyplot as plt

folder = r"past_games/20200427_144916_game"


def render(folder):
    for filename in os.listdir(folder):
        if filename.endswith(".p"):
            with open(os.path.join(folder, filename), "rb") as f:
                renderer, snapshots = pickle.load(f)

            for i, snapshot in enumerate(snapshots):
                renderer(snapshot, i)
                plt.savefig(os.path.join(folder, f"{i}"))
                plt.close()


if __name__ == "__main__":
    render(folder)
