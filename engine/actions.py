"""
Action system for Slay.

Enumerates all legal actions for the current player.
Actions are data objects — the engine applies them.
This separation is critical for AI: the AI picks from legal actions,
the engine validates and executes.
"""

from enum import Enum, auto
from .units import UnitType, unit_power, combine_units, PEASANT_COST, CASTLE_COST


class ActionType(Enum):
    BUY_PEASANT = auto()   # Buy peasant and place in territory
    BUY_CASTLE = auto()    # Buy castle and place in territory
    MOVE_UNIT = auto()     # Move/attack/combine a unit
    END_TURN = auto()      # End the current turn


class Action:
    __slots__ = ["type", "from_pos", "to_pos", "territory_idx"]

    def __init__(self, action_type, from_pos=None, to_pos=None, territory_idx=None):
        self.type = action_type
        self.from_pos = from_pos    # (col, row) source
        self.to_pos = to_pos        # (col, row) target
        self.territory_idx = territory_idx  # index into player's territories

    def __repr__(self):
        if self.type == ActionType.END_TURN:
            return "Action(END_TURN)"
        elif self.type == ActionType.BUY_PEASANT:
            return f"Action(BUY_PEASANT, territory={self.territory_idx}, at={self.to_pos})"
        elif self.type == ActionType.BUY_CASTLE:
            return f"Action(BUY_CASTLE, territory={self.territory_idx}, at={self.to_pos})"
        elif self.type == ActionType.MOVE_UNIT:
            return f"Action(MOVE, {self.from_pos} -> {self.to_pos})"
        return f"Action({self.type})"

    def __eq__(self, other):
        if not isinstance(other, Action):
            return False
        return (self.type == other.type and self.from_pos == other.from_pos
                and self.to_pos == other.to_pos and self.territory_idx == other.territory_idx)

    def __hash__(self):
        return hash((self.type, self.from_pos, self.to_pos, self.territory_idx))


def get_legal_actions(game_state):
    """
    Enumerate all legal actions for the current player.
    Returns a list of Action objects.
    """
    actions = []
    player_id = game_state.current_player.id
    player_territories = game_state.get_player_territories(player_id)

    for t_idx, territory in enumerate(player_territories):
        # --- Buy Peasant ---
        if territory.gold >= PEASANT_COST:
            for h in territory.hexes:
                # Place on empty land, grave, or tree
                if h.is_empty_land or h.grave or h.has_tree:
                    actions.append(Action(
                        ActionType.BUY_PEASANT,
                        to_pos=h.pos,
                        territory_idx=t_idx,
                    ))
                # Combine with existing unit (if not already baron)
                elif h.has_combat_unit:
                    combined = combine_units(h.unit, UnitType.PEASANT)
                    if combined is not None:
                        actions.append(Action(
                            ActionType.BUY_PEASANT,
                            to_pos=h.pos,
                            territory_idx=t_idx,
                        ))

        # --- Buy Castle ---
        if territory.gold >= CASTLE_COST:
            for h in territory.hexes:
                if (h.is_empty_land or h.grave) and not h.has_castle and not h.has_capital:
                    actions.append(Action(
                        ActionType.BUY_CASTLE,
                        to_pos=h.pos,
                        territory_idx=t_idx,
                    ))

        # --- Move Units ---
        for h in territory.movable_units:
            power = unit_power(h.unit)
            territory_hex_set = set(hx.pos for hx in territory.hexes)

            # All hexes this unit could move to
            # 1. Within territory: empty land, trees, combinable units
            for target in territory.hexes:
                if target.pos == h.pos:
                    continue
                if target.is_empty_land or target.grave:
                    actions.append(Action(
                        ActionType.MOVE_UNIT,
                        from_pos=h.pos,
                        to_pos=target.pos,
                    ))
                elif target.has_tree:
                    actions.append(Action(
                        ActionType.MOVE_UNIT,
                        from_pos=h.pos,
                        to_pos=target.pos,
                    ))
                elif target.has_combat_unit:
                    combined = combine_units(target.unit, h.unit)
                    if combined is not None:
                        actions.append(Action(
                            ActionType.MOVE_UNIT,
                            from_pos=h.pos,
                            to_pos=target.pos,
                        ))

            # 2. Attack: adjacent enemy hexes where power > defense
            for target in territory.neighboring_hexes(game_state.grid):
                if target.owner == player_id:
                    continue
                defense = game_state.grid.get_relative_power(target)
                if power > defense:
                    actions.append(Action(
                        ActionType.MOVE_UNIT,
                        from_pos=h.pos,
                        to_pos=target.pos,
                    ))

    # Always can end turn
    actions.append(Action(ActionType.END_TURN))

    return actions


def apply_action(game_state, action):
    """
    Apply an action to the game state. Returns True if successful.
    """
    if action.type == ActionType.END_TURN:
        game_state.end_turn()
        return True

    player_id = game_state.current_player.id
    player_territories = game_state.get_player_territories(player_id)

    if action.type == ActionType.BUY_PEASANT:
        if action.territory_idx >= len(player_territories):
            return False
        territory = player_territories[action.territory_idx]
        target = game_state.grid.get(*action.to_pos)
        if target is None:
            return False
        return game_state.buy_peasant(territory, target)

    elif action.type == ActionType.BUY_CASTLE:
        if action.territory_idx >= len(player_territories):
            return False
        territory = player_territories[action.territory_idx]
        target = game_state.grid.get(*action.to_pos)
        if target is None:
            return False
        return game_state.buy_castle(territory, target)

    elif action.type == ActionType.MOVE_UNIT:
        from_hex = game_state.grid.get(*action.from_pos)
        to_hex = game_state.grid.get(*action.to_pos)
        if from_hex is None or to_hex is None:
            return False
        return game_state.move_unit(from_hex, to_hex)

    return False
