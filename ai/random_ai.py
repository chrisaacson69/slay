"""
Random AI baseline for Slay.

Makes random legal moves each turn. Useful as:
- Opponent for manual testing
- Baseline for comparing smarter AIs
- Smoke test for the action system
"""

import random
from engine.actions import get_legal_actions, apply_action, ActionType


class RandomAI:
    def __init__(self, player_id, end_turn_weight=0.1):
        self.player_id = player_id
        self.end_turn_weight = end_turn_weight
        self.last_turn_log = []

    def take_turn(self, game_state):
        """Execute a full turn of random actions."""
        max_actions = 50  # Safety limit
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

            # Bias away from END_TURN so the AI actually does things
            non_end = [a for a in legal if a.type != ActionType.END_TURN]
            if non_end and random.random() > self.end_turn_weight:
                action = random.choice(non_end)
            else:
                action = next(a for a in legal if a.type == ActionType.END_TURN)

            self.last_turn_log.append(str(action))
            apply_action(game_state, action)
            actions_taken += 1

            if action.type == ActionType.END_TURN:
                break

        return actions_taken
