import logging
import random
import copy
import time
import numpy as np

import rules


def get_set(cards):
    card_set = []
    if "1" in cards and "2" in cards and "3" in cards:
        card_set = ["1", "2", "3"]
    s = "".join(cards)
    for c in ["1", "2", "3"]:
        if s.count(str(c)) == 3:
            card_set = [c] * 3
            break
    return card_set


def pop_card_set(cards):
    card_set = get_set(cards)
    [cards.remove(c) for c in card_set]
    return card_set


class Player:
    def __init__(self, nation):
        self.nation = nation
        self.cards = []
        self.is_alive = True
        self.gets_card = False

    def __repr__(self):
        return self.nation

    def get_deployment(self, game):
        n = game.get_deploy_num(self.nation)
        logging.debug(
            f"{self} gets {n} troops from {len(game.get_territories(self.nation))} territories."
        )
        return n

    def deploy(self, game, territory, num_troops):
        logging.debug(f"{self} deploys {num_troops} on {territory}")
        game.adjust_troops(territory, num_troops)

    def trade_cards(self, game):
        card_set = pop_card_set(self.cards)
        if card_set:
            logging.debug(f"{self.nation} traded cards for {rules.CARD_BONUS} troops.")
            return rules.CARD_BONUS
        return 0

    def play_turn(self, game):
        # Attack a random neighboring territory
        targets = game.get_out_border(self.nation)
        target = random.choice(list(targets.keys()))
        source = random.choice(targets[target])

        deployment = self.get_deployment(game)
        deployment += self.trade_cards(game)

        # deploy
        self.deploy(game, source, deployment)

        # attack
        game.battle(source, target, 4, 3, 0.5)

        # Has another player been defeated?
        if len(self.cards) >= 5 and not game.win_condition():
            deployment = self.trade_cards(game)
            targets = game.get_out_border(self.nation)
            target = random.choice(list(targets.keys()))
            source = random.choice(targets[target])
            game.adjust_troops(source, deployment)

        # reinforce // skip


class Player2(Player):

    def ranked_targets(self, game):
        targets = game.get_out_border(self.nation)
        ranking = []
        for target, sources in targets.items():
            source, troops = \
                sorted([(s, game.get_troops(s)) for s in sources], key=lambda x: -x[1])[0]
            score = (troops - 3) / game.get_troops(target)
            ranking.append((source, target, score))
        return sorted(ranking, key=lambda x: -x[2])

    def play_turn(self, game):
        # Attack weakly defended areas, and create a fortified perimeter
        # Find where to deploy
        ranked_targets = self.ranked_targets(game)
        for target in ranked_targets:
            if target[2] < 1.0:
                break

        # Deploy
        deploy = self.get_deployment(game) + self.trade_cards(game)
        self.deploy(game, target[0], deploy)

        # Pick off targets
        source, target, score = ranked_targets[0]
        while True:
            if score < 0:
                break
            game.battle(source, target, 3, 0.2, 5)
            ranked_targets = self.ranked_targets(game)
            if len(ranked_targets) == 0 or ranked_targets[0][2] < 1.0:
                break
            source, target, _ = ranked_targets[0]

        # Fortify - find non-border troops and move them to the weakest border link
        # border = set([s for t, ss in game.get_out_border(self.nation).items() for s in ss])
        border = game.get_in_border(self.nation)
        land_locked_troops = []
        for t in game.get_territories(self.nation):
            if t in border:
                continue
            elif game.get_troops(t) > 1:
                land_locked_troops.append((t, game.get_troops(t)))

        if len(land_locked_troops) == 0:
            return

        source, stack = sorted(land_locked_troops, key=lambda x: -x[1])[0]
        ranked_border = sorted(self.ranked_targets(game), key=lambda x: -x[2])
        for target, _, _ in ranked_border:
            if game.has_path(source, target):
                game.fortify(source, target, stack-1)
                break


class Player3(Player):

    def _get_continent_data(self, game):
        enemy_troops_by_continent = {c: 0 for c in game.continents}
        unowned_territories_per_continent = {c: 0 for c in game.continents}
        enemy_continents = set()
        my_continents = set()
        for t in game.get_all_territories():
            if game.get_nation(t) != self.nation:
                enemy_troops_by_continent[game.get_continent(t)] += game.get_troops(t)
                unowned_territories_per_continent[game.get_continent(t)] += 1
        for c, ts in game.continents.items():
            is_whole = True
            nation = game.get_nation(ts[0])  # candidate for continent ownership
            for t in ts[1:]:
                if game.get_nation(t) != nation:  # no continent
                    is_whole = False
                    break
            if is_whole:
                if nation == self.nation:
                    my_continents.add(c)
                else:
                    enemy_continents.add(c)
        return enemy_troops_by_continent, unowned_territories_per_continent, enemy_continents, my_continents

    def fight_scores(self, game):
        fight_scores_by_source = {}  # for deploy calc
        fight_scores = []  # for fighting
        enmy_trps_by_ctnt, unowned_tertrs_by_ctnt, enmy_ctnts, _ = self._get_continent_data(game)
        border = game.get_out_border(self.nation)
        for et, mts in border.items():  # et = enemy territory, mts = my territories
            # Get scores for all territories to attack from
            mt_scores = []
            for mt in mts:
                # base_score = (
                #     min(game.get_troops(mt) - game.get_troops(et) - 3, 4)
                #     + max(3 - game.get_troops(et), 0) / 2
                # )
                base_score = (game.get_troops(mt) - 3) / game.get_troops(et)
                # continent_build_score = max(
                #     (
                #         game.continent_bonuses[game.get_continent(et)] * 3
                #         - enmy_trps_by_ctnt[game.get_continent(et)]
                #     ) / unowned_tertrs_by_ctnt[game.get_continent(et)]
                #     , 0
                # )
                continent_build_score = max(
                    game.continent_bonuses[game.get_continent(et)] * 3
                    - enmy_trps_by_ctnt[game.get_continent(et)]
                ,0
                ) / 10
                continent_break_score = max(
                    (
                        game.continent_bonuses[game.get_continent(et)] * 2
                        - game.get_troops(et)
                    ) if game.get_continent(et) in enmy_ctnts else 0,
                    0
                )
                if base_score < 0:
                    score = base_score
                else:
                    score = base_score + continent_build_score + continent_break_score
                mt_scores.append((mt, score))
            best_mt, best_score = sorted(mt_scores, key=lambda x: -x[1])[0]
            fight_scores_by_source[best_mt] = best_score
            fight_scores.append((best_mt, et, best_score))
        return fight_scores, fight_scores_by_source

    def defense_scores(self, game):
        _, _, _, my_continents = self._get_continent_data(game)
        defense_scores_by_source = {}
        continent_trigger = False
        enemies_trigger = False
        for t in game.get_territories(self.nation):
            surrounding_enemies = 0
            for n in [t, *game.get_neighbors(t)]:
                if game.get_nation(n) == self.nation:
                    if game.get_continent(n) in my_continents:
                        continent_trigger = True
                else:
                    surrounding_enemies += game.get_troops(n)
                    enemies_trigger = True
            if enemies_trigger and continent_trigger:  # this is a bridge, should be fortified
                score = surrounding_enemies
            else:
                score = min(surrounding_enemies, 3)
            defense_scores_by_source[t] = score
        return defense_scores_by_source

    def play_turn(self, game):
        # Try to get continents, stomp on easy targets, defend continents, break other's continents
        fight_scores, fight_scores_by_source = self.fight_scores(game)
        if len(fight_scores) > 0:
            source, target, score = sorted(fight_scores, key=lambda x: -x[2])[0]
        else:
            source = game.get_territories(self.nation)[0]

        # DEPLOY
        deploy_num = self.get_deployment(game) + self.trade_cards(game)
        self.deploy(game, source, deploy_num)

        # FIGHT
        while True:
            fight_scores, fight_scores_by_source = self.fight_scores(game)
            if len(fight_scores) == 0:
                break
            source, target, score = sorted(fight_scores, key=lambda x: -x[2])[0]
            if score < 0:
                break
            game.battle(source, target, 3, 0.2, 3)

        # FORTIFY
        defense_scores_by_source = self.defense_scores(game)
        fortify_scores_by_source = {}
        for t in defense_scores_by_source:
            fortify_scores_by_source[t] = (
                    defense_scores_by_source[t]
                    - game.get_troops(t)
            )
        fortify_scores_ranked = sorted(list(fortify_scores_by_source.items()), key=lambda x: -x[1])
        fortify_pairs = []
        for source, ss in fortify_scores_ranked:
            for target, ts in fortify_scores_ranked:
                if source == target:
                    continue
                if game.has_path(source, target):
                    fortify_pairs.append((source, target, ts - ss))
        if len(fortify_pairs) > 0:
            source, target, troop_request = sorted(fortify_pairs, key=lambda x: -x[2])[0]
            troops = min(troop_request, game.get_troops(source) - 1)
            if troops > 0:
                game.fortify(source, target, troops)


class Player4(Player2):


    def ranked_targets(self, game):
        enemy_troops_by_continent = {c: 0 for c in game.continents}
        for t in game.get_all_territories():
            if game.get_nation(t) != self.nation:
                enemy_troops_by_continent[game.get_continent(t)] += game.get_troops(t)
        continent_attraction = {}
        for c, enemy_troops in enemy_troops_by_continent.items():
            if enemy_troops_by_continent[c] == 0:
                continent_attraction[c] = 0
                continue
            continent_attraction[c] = game.continent_bonuses[c] * 4 / enemy_troops_by_continent[c]

        targets = game.get_out_border(self.nation)
        ranking = []
        for target, sources in targets.items():
            source, troops = \
                sorted([(s, game.get_troops(s)) for s in sources], key=lambda x: -x[1])[0]
            score = (troops - 3) / game.get_troops(target) \
                    + continent_attraction[game.get_continent(target)] * 0.2
            if troops < 3:
                score = 0
            ranking.append((source, target, score))
        return sorted(ranking, key=lambda x: -x[2])

    def play_turn(self, game):
        # Attack weakly defended areas, and create a fortified perimeter
        # Find where to deploy
        ranked_targets = self.ranked_targets(game)
        for target in ranked_targets:
            if target[2] < 1.0:
                break

        # Deploy
        deploy = self.get_deployment(game) + self.trade_cards(game)
        self.deploy(game, target[0], deploy)

        # Pick off targets
        source, target, score = ranked_targets[0]
        while True:
            if score < -0.38:
                break
            game.battle(source, target, 3, 0.2, 3)
            ranked_targets = self.ranked_targets(game)
            if len(ranked_targets) == 0 or ranked_targets[0][2] < 1.0:
                break
            source, target, _ = ranked_targets[0]

        # Fortify - find non-border troops and move them to the weakest border link
        # border = set([s for t, ss in game.get_out_border(self.nation).items() for s in ss])
        border = game.get_in_border(self.nation)
        land_locked_troops = []
        for t in game.get_territories(self.nation):
            if t in border:
                continue
            elif game.get_troops(t) > 1:
                land_locked_troops.append((t, game.get_troops(t)))

        if len(land_locked_troops) == 0:
            return

        source, stack = sorted(land_locked_troops, key=lambda x: -x[1])[0]
        ranked_border = sorted(self.ranked_targets(game), key=lambda x: -x[2])
        for target, _, _ in ranked_border:
            if game.has_path(source, target):
                game.fortify(source, target, stack-1)
                break


class Player5(Player2):

    def get_position_score(self, game):
        troop_count = game.get_total_troops(self.nation)
        deploy_num = game.get_deploy_num(self.nation)

        score = (
            troop_count
            + deploy_num * 2
        )
        return score

    class Path:
        def __init__(self, start_territory, troops):
            self.nodes_list = [start_territory]
            self.node_set = {start_territory}
            self.end_troops = troops
            self.score = -1e10

        def add(self, territory, killed_troops):
            self.nodes_list.append(territory)
            self.node_set.add(territory)
            self.end_troops -= killed_troops

    def play_turn(self, game):
        # Deploy
        deploy = self.get_deployment(game) + self.trade_cards(game)

        # Create paths
        in_border = game.get_in_border(self.nation)
        owned_territories = copy.deepcopy(game.get_territories(self.nation))
        paths = []  # TODO set explorable paths here to allow no attacks (fix cards)
        t0 = time.time()
        explorable_paths = [self.Path(t, game.get_troops(t) + deploy) for t in in_border]
        while len(paths) < 1e3:
            new_paths = []
            for path in explorable_paths:
                end = path.nodes_list[-1]
                neighbors = game.get_neighbors(end)
                for neighbor in neighbors:
                    if neighbor in owned_territories or neighbor in path.node_set:
                        continue
                    enemy_troops = game.get_troops(neighbor)
                    if path.end_troops - enemy_troops >= 3:
                        new_path = copy.deepcopy(path)
                        new_path.add(neighbor, killed_troops=enemy_troops)
                        # TODO manage killed troops better
                        # TODO manage stop point more flexibly
                        new_paths.append(new_path)
            if new_paths:
                explorable_paths = new_paths
                paths.extend(explorable_paths)
            else:
                break
        logging.debug(f"Found {len(paths)} paths in {(time.time()-t0)*1000:.0f} ms")

        t0 = time.time()
        # Evaluate paths
        eval_game = copy.deepcopy(game)
        # eval_game = game  # TODO remove the deepcopy
        for path in paths:
            # Create eval game
            revert_nodes = []
            for t in path.nodes_list:
                revert_nodes.append({
                    "territory": t,
                    "nation": game.get_nation(t),
                    "troops": game.get_troops(t)
                })
                eval_game.set_nation(t, self.nation)
                eval_game.set_troops(t, 1 if t != path.nodes_list[-1] else path.end_troops)
            path.score = self.get_position_score(eval_game)
            # Revert eval game
            for rn in revert_nodes:
                eval_game.set_nation(rn["territory"], rn["nation"])
                eval_game.set_troops(rn["territory"], rn["troops"])

        # Get best path
        if len(paths) == 0:
            best_path = self.Path(next(iter(game.get_territories(self.nation))), 0)
        else:
            best_path = sorted(paths, key=lambda x: -x.score)[0]
        logging.debug(f"Found best path, score: {best_path.score} in {(time.time()-t0)*1000:.0f} ms")
        logging.debug(f"Best path: {best_path.nodes_list}")

        # Play best path
        # Deploy
        s = best_path.nodes_list[0]
        self.deploy(game, s, deploy)

        for t in best_path.nodes_list[1:]:
            game.battle(s, t, 3, 0.5, 1)
            if game.get_nation(t) != self.nation:
                break
            s = t

        # TODO Fortify
        # Fortify - find non-border troops and move them to the weakest border link
        # border = set([s for t, ss in game.get_out_border(self.nation).items() for s in ss])
        border = game.get_in_border(self.nation)
        land_locked_troops = []
        for t in game.get_territories(self.nation):
            if t in border:
                continue
            elif game.get_troops(t) > 1:
                land_locked_troops.append((t, game.get_troops(t)))

        if len(land_locked_troops) == 0:
            return

        source, stack = sorted(land_locked_troops, key=lambda x: -x[1])[0]
        ranked_border = sorted(self.ranked_targets(game), key=lambda x: -x[2])
        for target, _, _ in ranked_border:
            if game.has_path(source, target):
                game.fortify(source, target, stack-1)
                break


class Player6(Player2):

    def __init__(self, nation):
        # self.dna = dna
        super().__init__(nation)

    def get_position_score(self, game):
        troop_count = game.get_total_troops(self.nation)
        deploy_num = game.get_deploy_num(self.nation)
        other_nation_territories = \
            len(game.territory_ownership) - len(game.get_territories(self.nation))

        in_border = game.get_in_border(self.nation)
        out_border = game.get_in_border(self.nation)
        in_lands = set([t for t in game.get_territories(self.nation) if t not in in_border])
        protective_border = []
        for t in in_border:
            for n in game.get_neighbors(t):
                if n in in_lands:
                    protective_border.append(t)
                    break

        border_strength = 0
        if protective_border:
            border_strength = np.power(
                np.product([game.get_troops(t) for t in protective_border]),
                1/len(protective_border)
            )
        border_strength = min(border_strength, max([game.get_troops(t) for t in out_border]+[10]))

        other_nations_production = sum([game.get_deploy_num(n) for n in game.nations if n != self.nation])

        # TODO include cards somehow
        score = (
            troop_count
            + deploy_num * 2
            + border_strength
            - other_nations_production * 0.5
            + 1000 * (other_nation_territories == 0)
            # - len(game.get_territories(nation))
            # + border_troops * 2
            # - enemy_border_troops * 4
        )
        return score

    class Path:
        def __init__(self, start_territory, troops):
            self.nodes_list = [start_territory]
            self.node_set = {start_territory}
            self.end_troops = troops
            self.score = -1e10

        def add(self, territory, killed_troops):
            self.nodes_list.append(territory)
            self.node_set.add(territory)
            self.end_troops -= killed_troops

    def play_turn(self, game):
        # Deploy
        deploy = self.get_deployment(game) + self.trade_cards(game)

        # Create paths
        in_border = game.get_in_border(self.nation)
        owned_territories = copy.deepcopy(game.get_territories(self.nation))
        paths = []  # TODO set explorable paths here to allow no attacks (fix cards)
        t0 = time.time()
        explorable_paths = [self.Path(t, game.get_troops(t) + deploy) for t in in_border]
        while len(paths) < 1e3:
            new_paths = []
            for path in explorable_paths:
                end = path.nodes_list[-1]
                neighbors = game.get_neighbors(end)
                for neighbor in neighbors:
                    if neighbor in owned_territories or neighbor in path.node_set:
                        continue
                    enemy_troops = game.get_troops(neighbor)
                    if path.end_troops - enemy_troops >= 3:
                        new_path = copy.deepcopy(path)
                        new_path.add(neighbor, killed_troops=enemy_troops)
                        # TODO manage killed troops better
                        # TODO manage stop point more flexibly
                        new_paths.append(new_path)
            if new_paths:
                explorable_paths = new_paths
                paths.extend(explorable_paths)
            else:
                break

        # Create a copy of each path that fortifies to start
        for i in range(len(paths)):
            home_fort_alt_path = copy.deepcopy(paths[i])
            home_fort_alt_path.nodes_list.append(home_fort_alt_path.nodes_list[0])
            paths.append(home_fort_alt_path)
        logging.debug(f"Found {len(paths)} paths in {(time.time()-t0)*1000:.0f} ms")

        t0 = time.time()
        # Evaluate paths
        eval_game = copy.deepcopy(game)
        # eval_game = game  # TODO remove the deepcopy
        for path in paths:
            # Create eval game
            revert_nodes = []
            for t in path.nodes_list:
                revert_nodes.append({
                    "territory": t,
                    "nation": game.get_nation(t),
                    "troops": game.get_troops(t)
                })
                eval_game.set_nation(t, self.nation)
                eval_game.set_troops(t, 1 if t != path.nodes_list[-1] else path.end_troops)
            path.score = self.get_position_score(eval_game)
            # Revert eval game
            for rn in revert_nodes:
                eval_game.set_nation(rn["territory"], rn["nation"])
                eval_game.set_troops(rn["territory"], rn["troops"])

        # Get best path
        if len(paths) == 0:
            best_path = self.Path(next(iter(game.get_territories(self.nation))), 0)
        else:
            best_path = sorted(paths, key=lambda x: -x.score)[0]
        logging.debug(f"Found best path, score: {best_path.score} in {(time.time()-t0)*1000:.0f} ms")
        logging.debug(f"Best path: {best_path.nodes_list}")

        # Play best path
        # Deploy
        s = best_path.nodes_list[0]
        self.deploy(game, s, deploy)

        if len(best_path.nodes_list) == 1:
            return

        unfinished_path = False
        for t in best_path.nodes_list[1:-1]:
            game.battle(s, t, 3, 0.5, 1)
            if game.get_nation(t) != self.nation:  # capture failed
                unfinished_path = True
                break
            s = t
        # Last command a fortify or not?
        if game.get_nation(best_path.nodes_list[-1]) == self.nation:
            # Yes
            troops_left = game.get_troops(best_path.nodes_list[-2])
            if troops_left > 1:
                game.fortify(best_path.nodes_list[-2], best_path.nodes_list[-1], troops_left-1)
            return
        elif not unfinished_path:  # Can still continue
            game.battle(best_path.nodes_list[-2], best_path.nodes_list[-1], 3, 0.5, 1)

        # Fortify any inland troops, or normalize the borders TODO normalize borders
        border = game.get_in_border(self.nation)
        land_locked_troops = []
        for t in game.get_territories(self.nation):
            if t in border:
                continue
            elif game.get_troops(t) > 1:
                land_locked_troops.append((t, game.get_troops(t)))

        if len(land_locked_troops) == 0:
            return
        source, stack = sorted(land_locked_troops, key=lambda x: -x[1])[0]
        ranked_border = sorted(border, key=lambda x: game.get_troops(x))
        for target in ranked_border:
            if game.has_path(source, target):
                game.fortify(source, target, stack-1)
                break
