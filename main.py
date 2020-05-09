import os
import sys
import networkx as nx
import _pickle as pickle

from players import *
from maps.classic import map_info
from game_render import render

storage_folder = f"past_games/{time.strftime('%Y%m%d_%H%M%S')}_game"
os.makedirs(storage_folder)

logging.basicConfig(
    format="%(message)s",
    filename=f"{storage_folder}/game.log",
    filemode="w",
    level=logging.DEBUG
)
logging.getLogger().addHandler(logging.StreamHandler(sys.stdout))
logging.StreamHandler().setLevel(logging.DEBUG)
logging.getLogger('matplotlib.font_manager').disabled = True


def dice_roll():
    return random.choice(list(range(6))) + 1


def dice_battle(att_n, def_n):
    att_rolls = sorted([dice_roll() for _ in range(att_n)], reverse=True)
    def_rolls = sorted([dice_roll() for _ in range(def_n)], reverse=True)

    att_loss, def_loss = 0, 0
    for i in range(min(len(att_rolls), len(def_rolls))):
        if att_rolls[i] > def_rolls[i]:
            def_loss += 1
        else:
            att_loss += 1

    return att_loss, def_loss


def expected_loss(defenders):
    if defenders <= 5:
        return {1: 0.516, 2: 1.547, 3: 2.307, 4: 3.210, 5: 4.037}[defenders]
    else:
        return 0.8537 * defenders + 1.4817


class Game:
    def __init__(self, map_info, players):
        self.players = {p.nation: p for p in players}
        self.round_num = 0
        self.ply = 0
        # Setup map
        self.g = map_info["graph"]
        self.nations = map_info["nations"]
        self.continents = map_info["continent_definition"]
        self.continent_bonuses = map_info["continent_bonuses"]
        self.renderer = map_info["renderer"]
        self.snapshots = []
        self.nation_territories = {}
        for t in self.g.nodes:
            self.nation_territories.setdefault(self.g.nodes[t]["nation"], set()).add(t)
        self.territory_ownership = {t: self.g.nodes[t]["nation"] for t in self.g.nodes}  # for speed
        self.territory_troops = {t: self.g.nodes[t]["troops"] for t in self.g.nodes}  # for speed
        self.territory_continent = {t: self.g.nodes[t]["continent"] for t in self.g.nodes}  # idem

    def get_all_territories(self):
        return set([t for n in self.nations for t in self.nation_territories[n]])

    def get_territories(self, nation):
        return self.nation_territories[nation]

    def get_neighbors(self, territory):
        return self.g.neighbors(territory)

    def get_nation(self, territory):
        # return self.g.nodes[territory]["nation"]
        return self.territory_ownership[territory]

    def get_player(self, territory):
        return self.players[self.get_nation(territory)]

    def get_troops(self, territory):
        # return self.g.nodes[territory]["troops"]
        return self.territory_troops[territory]

    def get_continent(self, territory):
        return self.territory_continent[territory]

    def get_continent_territories(self, continent):
        return self.continents[continent]

    def get_total_troops(self, nation):
        return sum([self.get_troops(t) for t in self.get_territories(nation)])

    def set_troops(self, territory, troops):
        self.g.nodes[territory]["troops"] = troops
        self.territory_troops[territory] = troops

    def adjust_troops(self, territory, troop_adjustment):
        self.g.nodes[territory]["troops"] += troop_adjustment
        self.territory_troops[territory] += troop_adjustment

    def set_nation(self, territory, nation):
        original_nation = self.get_nation(territory)
        self.g.nodes[territory]["nation"] = nation
        self.nation_territories[original_nation].remove(territory)
        self.nation_territories[nation].add(territory)
        self.territory_ownership[territory] = nation

    def has_path(self, t1, t2):
        try:
            return nx.has_path(self.g.subgraph(self.get_territories(self.get_nation(t1))), t1, t2)
        except nx.NodeNotFound:
            return False

    def get_deploy_num(self, nation):
        territories = self.get_territories(nation)
        # check continents
        territories_split_by_continent = {}
        for t in territories:
            territories_split_by_continent.setdefault(self.get_continent(t), []).append(t)
        continent_bonus = 0
        for c in self.continents:
            if len(self.continents[c]) == len(territories_split_by_continent.get(c, [])):
                continent_bonus += self.continent_bonuses[c]

        return max(len(territories) // 3, 3) + continent_bonus

    def battle(self, t1, t2, att_until, target_leave_frac, leave_cap):
        # check different nations
        if self.get_nation(t1) == self.get_nation(t2):
            logging.warning("Cannot attack own territory")
            return
        f1 = self.get_troops(t1)
        f2 = self.get_troops(t2)
        # check enough troops to attack
        if f1 < 2:
            logging.warning("Not enough troops to attack")
            return

        fi1 = f1
        fi2 = f2
        while f1 >= att_until and f2 > 0:
            att_loss, def_loss = dice_battle(min(3, f1 - 1), min(2, f2))
            f1 -= att_loss
            f2 -= def_loss

        logging.debug(
            f"{t1} ({fi1}) attacks {t2} ({fi2}) of {self.get_nation(t2)}: ({f1-fi1}, {f2-fi2})."
        )

        if f2 == 0:  # Territory has been conquered
            logging.debug(f"{self.get_nation(t1)} takes {t2} from {self.get_nation(t2)}!")
            attacking_player = self.get_player(t1)
            attacking_player.gets_card = True
            # Check defeat
            if len(self.get_territories(self.get_nation(t2))) == 1:
                logging.debug(f"{self.get_nation(t2)} has been defeated!")
                defeated_player = self.get_player(t2)
                defeated_player.is_alive = False
                # Transfer cards
                attacking_player.cards += defeated_player.cards
                defeated_player.cards = []

            self.set_nation(t2, self.get_nation(t1))
            leave = max(min(int(f1 * target_leave_frac), leave_cap), 1)
            f2 = f1 - leave
            f1 = leave

        self.set_troops(t1, f1)
        self.set_troops(t2, f2)

    def fortify(self, source, target, troops):
        if self.has_path(source, target) and self.get_troops(source) > troops:
            self.adjust_troops(source, -troops)
            self.adjust_troops(target, troops)
            logging.debug(f"Fortified {troops} troops from {source} to {target}.")
        else:
            logging.error(f"Cannot fortify {troops} troops from {source} to {target}, no path.")

    def get_out_border(self, nation):
        targets = {}
        for t in self.get_territories(nation):
            for tn in self.get_neighbors(t):
                if self.get_nation(tn) == nation:
                    continue
                targets.setdefault(tn, []).append(t)
        return targets

    def get_in_border(self, nation):
        border = {}
        for t in self.get_territories(nation):
            for tn in self.get_neighbors(t):
                if self.get_nation(tn) == nation:
                    continue
                border.setdefault(t, []).append(tn)
        return border

    def draw_card(self, player):
        if player.gets_card:
            player.cards.append(random.choice(["1", "2", "3"]))
            player.gets_card = False

    def win_condition(self):
        return len([p for p in self.players.values() if p.is_alive]) == 1

    def get_image(self):
        self.renderer(self.g, self.round_num)

    def save_snapshot(self, active):
        if active:
            self.snapshots.append(copy.deepcopy(self.g))

    def export_snapshots(self, active):
        if active:
            with open(f"{storage_folder}/snapshots.p", "wb") as f:
                pickle.dump((self.renderer, self.snapshots), f)

    def __repr__(self):
        output = ""
        for nation in self.nations:
            territories = self.get_territories(nation)
            output += "----------\n"
            output += (
                f"{nation}: {len(territories)}, "
                f"{self.get_total_troops(nation)}, "
                f"{len(self.players[nation].cards)}\n"
            )
            for territory in territories:
                output += f"   {territory}: {self.get_troops(territory)}\n"
        return output


def run(game, snapshots_on):
    while True:
        logging.debug(f"==========\nRound {game.round_num}")
        logging.debug(game)
        for player in game.players.values():
            if player.is_alive:
                game.save_snapshot(snapshots_on)
                logging.debug(f"{player.nation} starting turn. Ply {game.ply}")
                player.play_turn(game)
                game.draw_card(player)
                if game.win_condition():
                    logging.debug(f"{player} wins!")
                    game.save_snapshot(snapshots_on)
                    game.export_snapshots(snapshots_on)
                    return player
                game.ply += 1
        game.round_num += 1


if __name__ == "__main__":

    players = [Player6("A"), Player2("B"), Player2("C"), Player2("D")]
    counts = {}
    t0 = time.time()

    num_games = 1

    snapshots_on = True
    if num_games >= 10:
        snapshots_on = False
        logging.getLogger().setLevel(logging.INFO)
    for i in range(num_games):
        game = Game(map_info=copy.deepcopy(map_info), players=copy.deepcopy(players))
        winner = run(game, snapshots_on)
        counts.setdefault(winner.nation, 0)
        counts[winner.nation] += 1

    logging.info(f"Results: {sorted(list(counts.items()), key=lambda x: -x[1])}".replace("'", ""))
    logging.info(f"{(time.time() - t0)*1000:.0f} ms")
    if num_games == 1:
        render(storage_folder)
