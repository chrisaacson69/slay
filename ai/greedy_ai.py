"""
Greedy heuristic AI for Slay.

Uses 1-ply lookahead: for each legal action, clone the state, apply the
action, and score the resulting board. Pick the highest-scoring action.
Repeat until END_TURN is the best option.
"""

from engine.actions import get_legal_actions, apply_action, ActionType
from engine.units import unit_power


def evaluate(game_state, player_id):
    """
    Score the board from player_id's perspective.
    Returns a float — higher is better for the player.
    """
    own_hexes = 0
    own_income = 0
    own_gold = 0
    own_power = 0

    enemy_hexes = 0
    enemy_power = 0

    for territory in game_state.territories:
        if territory.owner == player_id:
            own_hexes += territory.size
            own_income += territory.net_income
            own_gold += territory.gold
            for h in territory.combat_units:
                own_power += unit_power(h.unit)
        elif territory.owner >= 0:
            enemy_hexes += territory.size
            for h in territory.combat_units:
                enemy_power += unit_power(h.unit)

    # Weights tuned so buying a peasant (cost 10, wage 2, power 1) is
    # net-positive: -10*0.1 + -2*1 + 1*5 = +2.  Capturing a hex is also
    # clearly rewarded: +1*3 (own) + 1*2 (enemy lost) = +5 from hex swing.
    score = (
        own_hexes * 3
        + own_income * 1
        + own_gold * 0.1
        + own_power * 5
        - enemy_hexes * 2
        - enemy_power * 1.5
    )

    # Bankruptcy risk — penalize hard if any territory will go bankrupt
    for territory in game_state.get_player_territories(player_id):
        if territory.gold + territory.net_income < 0:
            score -= 30

    return score


class GreedyAI:
    def __init__(self, player_id):
        self.player_id = player_id
        self.last_turn_log = []

    def take_turn(self, game_state):
        """Execute a full turn using greedy 1-ply lookahead."""
        max_actions = 80
        actions_taken = 0
        self.last_turn_log = []

        while actions_taken < max_actions:
            if game_state.current_player.id != self.player_id:
                break
            if game_state.game_over:
                break

            legal = get_legal_actions(game_state)
            if not legal:
                break

            # Score the current state (baseline = what we get by ending turn)
            baseline_score = evaluate(game_state, self.player_id)

            best_action = None
            best_score = baseline_score

            for action in legal:
                if action.type == ActionType.END_TURN:
                    continue

                clone = game_state.clone()
                apply_action(clone, action)
                score = evaluate(clone, self.player_id)

                if score > best_score:
                    best_score = score
                    best_action = action

            # No action improves the board — end turn
            if best_action is None:
                self.last_turn_log.append("No improving action found — ending turn")
                apply_action(game_state, next(
                    a for a in legal if a.type == ActionType.END_TURN
                ))
                actions_taken += 1
                break

            # Apply the best action
            delta = best_score - baseline_score
            self.last_turn_log.append(f"{best_action}  (delta={delta:+.1f})")
            apply_action(game_state, best_action)
            actions_taken += 1

            if best_action.type == ActionType.END_TURN:
                break

        return actions_taken
