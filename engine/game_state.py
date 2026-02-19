"""
Core game state for Slay.

Manages the full state of the game:
- Hex grid
- Players and turn order
- Territory calculation
- Turn progression (income, tree growth, bankruptcy, victory)

This is the headless engine — no graphics, no UI.
Can be used for self-play, AI training, and testing.
"""

import random
from .hex_grid import HexGrid
from .territory import Territory
from .units import UnitType, unit_power, PEASANT_COST, CASTLE_COST, combine_units


class Player:
    def __init__(self, player_id):
        self.id = player_id
        self.alive = True
        self.is_human = False

    def __repr__(self):
        status = "alive" if self.alive else "dead"
        return f"Player({self.id}, {status})"


class GameState:
    def __init__(self, grid=None, num_players=2):
        self.grid = grid or HexGrid(16, 12)
        self.players = [Player(i) for i in range(num_players)]
        self.territories = []
        self.current_player_idx = 0
        self.turn_number = 0
        self.game_over = False
        self.winner = None

    @property
    def current_player(self):
        return self.players[self.current_player_idx]

    @property
    def num_alive(self):
        return sum(1 for p in self.players if p.alive)

    def get_player_territories(self, player_id):
        """All territories belonging to a player."""
        return [t for t in self.territories if t.owner == player_id]

    # =========================================================
    # Map Setup
    # =========================================================

    def setup_random_map(self, width=24, height=16, seed=None):
        """Generate a random island map with fragmented player territories."""
        if seed is not None:
            random.seed(seed)

        min_land = (width * height) // 4  # At least 25% of grid should be land

        # Retry island generation until we get a decent size
        for attempt in range(10):
            self.grid = HexGrid(width, height)
            center_col, center_row = width // 2, height // 2
            max_dist = min(width, height) * 0.55

            for h in self.grid.hexes.values():
                dc = h.col - center_col
                dr = h.row - center_row
                dist = (dc * dc + dr * dr) ** 0.5
                # High probability near center, tapers to edges
                prob = max(0, 1.0 - (dist / max_dist) ** 1.5)
                h.is_land = random.random() < prob * 0.85 + 0.05

            # Clean up: fill water holes, remove land specks
            for h in self.grid.hexes.values():
                if not h.is_land:
                    land_n = sum(
                        1 for n in self.grid.get_neighbors(h) if n.is_land
                    )
                    if land_n >= 5:
                        h.is_land = True
            for h in list(self.grid.all_land()):
                land_n = sum(
                    1 for n in self.grid.get_neighbors(h) if n.is_land
                )
                if land_n <= 1:
                    h.is_land = False

            self._keep_largest_landmass()

            if len(self.grid.all_land()) >= min_land:
                break

        land_hexes = self.grid.all_land()
        if not land_hexes:
            return

        # Scatter ownership: each hex randomly assigned to a player
        # with some left neutral — creates natural fragmentation
        num_players = len(self.players)
        neutral_chance = 0.12

        for h in land_hexes:
            if random.random() < neutral_chance:
                h.owner = -1  # Neutral
            else:
                h.owner = random.randint(0, num_players - 1)

        # Scatter some trees
        for h in self.grid.all_land():
            if h.unit == UnitType.NONE and random.random() < 0.08:
                if self.grid.is_coastal(h):
                    h.unit = UnitType.TREE_PALM
                else:
                    h.unit = UnitType.TREE_PINE

        self.refresh_territories()

        # All territories start with 10 gold, no units
        for t in self.territories:
            t.gold = 10

    def _keep_largest_landmass(self):
        """Remove all land not connected to the largest contiguous group."""
        land_hexes = self.grid.all_land()
        if not land_hexes:
            return

        # BFS to find all connected components (owner-agnostic, just land)
        visited = set()
        components = []
        for h in land_hexes:
            if h.pos in visited:
                continue
            component = []
            queue = [h]
            visited.add(h.pos)
            while queue:
                cur = queue.pop(0)
                component.append(cur)
                for n in self.grid.get_neighbors(cur):
                    if n.is_land and n.pos not in visited:
                        visited.add(n.pos)
                        queue.append(n)
            components.append(component)

        # Keep only the largest, sink the rest
        components.sort(key=len, reverse=True)
        for comp in components[1:]:
            for h in comp:
                h.is_land = False

    def load_map_data(self, map_data, width, height, player_assignments=None):
        """
        Load map from a 2D grid of ints and optional player assignments.
        map_data: 2D list of ints (0=water, 1=land, 2=pine, 3=palm)
        player_assignments: 2D list of ints (-1=unowned, 0+=player id)
        """
        self.grid = HexGrid(width, height)
        self.grid.load_map(map_data, width, height)

        if player_assignments:
            for row_idx, row in enumerate(player_assignments):
                for col_idx, owner in enumerate(row):
                    h = self.grid.get(col_idx, row_idx)
                    if h and h.is_land:
                        h.owner = owner

        self.refresh_territories()

    # =========================================================
    # Territory Management
    # =========================================================

    def refresh_territories(self, capital_avoid=None, merge_priority_pos=None):
        """
        Recalculate all territories from scratch via flood fill.
        Handles merges (sum gold, largest capital wins) and splits (0 gold).

        capital_avoid: optional dict {owner_id: set of (col,row)} —
            when placing a new capital for that owner, avoid those positions.
        merge_priority_pos: optional (col,row) — the attacking unit's
            source territory gets priority in same-size merge ties.
        """
        # Map old capital positions to (owner, gold, territory_size)
        old_caps = {}
        for t in self.territories:
            cap = t.capital_hex
            if cap:
                old_caps[cap.pos] = (t.owner, t.gold, t.size)

        # Which old territory contained the priority position?
        priority_cap_pos = None
        if merge_priority_pos:
            for t in self.territories:
                if any(h.pos == merge_priority_pos for h in t.hexes):
                    cap = t.capital_hex
                    if cap:
                        priority_cap_pos = cap.pos
                    break

        # Clear all capitals
        for h in self.grid.all_land():
            h.has_capital = False

        # Flood fill to find all territories
        visited = set()
        self.territories = []

        for h in self.grid.all_land():
            if h.pos in visited or h.owner < 0:
                continue
            region = self.grid.flood_fill(h, h.owner)
            for rh in region:
                visited.add(rh.pos)

            if region:
                t = Territory(region, h.owner)
                self.territories.append(t)

        # Restore gold and place capitals
        for t in self.territories:
            # Find all old capitals that are now in this territory
            merged_caps = []
            for h in t.hexes:
                if h.pos in old_caps:
                    prev_owner, prev_gold, prev_size = old_caps[h.pos]
                    if prev_owner == t.owner:
                        merged_caps.append((h.pos, prev_gold, prev_size))

            # Sum gold from all merged territories
            t.gold = sum(g for _, g, _ in merged_caps)

            # Pick capital from the largest old territory
            # Tie-break: attacker's source territory wins
            preferred_cap = None
            if merged_caps:
                merged_caps.sort(
                    key=lambda c: (c[2], c[0] == priority_cap_pos),
                    reverse=True,
                )
                preferred_cap = merged_caps[0][0]

            avoid = None
            if capital_avoid and t.owner in capital_avoid:
                avoid = capital_avoid[t.owner]
            t.ensure_capital(
                avoid_adjacent_to=avoid,
                preferred_pos=preferred_cap,
            )

    # =========================================================
    # Turn Progression
    # =========================================================

    def start_turn(self):
        """
        Called at the beginning of a player's turn.
        - Collect income for all territories
        - Handle bankruptcy
        - Reset unit movement
        - Grow trees
        """
        player = self.current_player
        if not player.alive:
            self.advance_turn()
            return

        # Reset movement for this player's units
        for h in self.grid.all_land():
            if h.owner == player.id and h.has_combat_unit:
                h.can_move = True

        # Collect income (skip on turn 0)
        if self.turn_number > 0:
            for t in self.get_player_territories(player.id):
                t.collect_income()

        # Grow trees
        self._grow_trees(player.id)

        # Refresh after potential bankruptcies
        self.refresh_territories()

        # Check if player is eliminated
        player_territories = self.get_player_territories(player.id)
        if not player_territories:
            player.alive = False

        # Check victory
        self._check_victory()

    def end_turn(self):
        """End the current player's turn and advance."""
        self.advance_turn()

    def advance_turn(self):
        """Move to the next player's turn."""
        self.current_player_idx = (self.current_player_idx + 1) % len(self.players)
        if self.current_player_idx == 0:
            self.turn_number += 1
        self.start_turn()

    def _grow_trees(self, player_id):
        """
        Tree growth — deterministic, one-shot (no cascading).

        1. Snapshot existing trees
        2. Convert graves → palm (coastal) or pine (inland)
        3. Spread trees using only the original snapshot:
           - Coastal empty hex + adjacent to 1+ original palm → palm
           - Non-coastal empty hex + adjacent to 2+ original pines → pine
        """
        # 1. Snapshot ALL trees on the map (any owner) BEFORE changes
        original_palms = set()
        original_pines = set()
        for h in self.grid.all_land():
            if h.unit == UnitType.TREE_PALM:
                original_palms.add(h.pos)
            elif h.unit == UnitType.TREE_PINE:
                original_pines.add(h.pos)

        # 2. Convert this player's graves to trees
        for h in self.grid.all_land():
            if h.owner != player_id or not h.grave:
                continue
            if self.grid.is_coastal(h):
                h.unit = UnitType.TREE_PALM
            else:
                h.unit = UnitType.TREE_PINE
            h.grave = False

        # 3. Spread trees onto this player's hexes only,
        #    but ANY player's trees can be the source
        new_trees = []
        for h in self.grid.all_land():
            if h.owner != player_id:
                continue
            # Must be truly empty: no unit, no structure, no grave
            if (h.unit != UnitType.NONE or h.has_capital
                    or h.has_castle or h.grave):
                continue

            neighbors = self.grid.get_neighbors(h)

            if self.grid.is_coastal(h):
                # Coastal: palm from any adjacent original palm
                has_original_palm = any(
                    n.pos in original_palms for n in neighbors
                )
                if has_original_palm:
                    new_trees.append((h, UnitType.TREE_PALM))
            else:
                # Inland: pine from 2+ adjacent original pines (any owner)
                original_pine_count = sum(
                    1 for n in neighbors
                    if n.pos in original_pines
                )
                if original_pine_count >= 2:
                    new_trees.append((h, UnitType.TREE_PINE))

        for h, tree_type in new_trees:
            h.unit = tree_type

    def _check_victory(self):
        """Check if only one player remains alive."""
        alive = [p for p in self.players if p.alive]
        if len(alive) <= 1:
            self.game_over = True
            self.winner = alive[0].id if alive else None

    # =========================================================
    # Actions
    # =========================================================

    def buy_peasant(self, territory, target_hex):
        """
        Buy a peasant and place on target hex within territory.
        Returns True if successful.
        """
        if territory.owner != self.current_player.id:
            return False
        if territory.gold < PEASANT_COST:
            return False
        if not territory.contains(target_hex):
            return False

        # Can place on empty land or combine with existing unit
        if target_hex.has_combat_unit:
            combined = combine_units(target_hex.unit, UnitType.PEASANT)
            if combined is None:
                return False
            target_hex.unit = combined
        elif target_hex.is_empty_land or target_hex.has_tree or target_hex.grave:
            target_hex.unit = UnitType.PEASANT
            target_hex.grave = False
        else:
            return False

        target_hex.can_move = True
        territory.gold -= PEASANT_COST
        return True

    def buy_castle(self, territory, target_hex):
        """
        Buy a castle/fort and place on target hex within territory.
        Returns True if successful.
        """
        if territory.owner != self.current_player.id:
            return False
        if territory.gold < CASTLE_COST:
            return False
        if not territory.contains(target_hex):
            return False
        if target_hex.has_castle or target_hex.has_capital:
            return False
        if target_hex.has_combat_unit:
            return False
        if not target_hex.is_land:
            return False

        target_hex.has_castle = True
        target_hex.grave = False
        target_hex.unit = UnitType.NONE
        territory.gold -= CASTLE_COST
        return True

    def move_unit(self, from_hex, to_hex):
        """
        Move a unit from one hex to another.
        Handles: moving within territory, attacking, combining.
        Returns True if successful.
        """
        player_id = self.current_player.id

        if from_hex.owner != player_id:
            return False
        if not from_hex.has_combat_unit:
            return False
        if not from_hex.can_move:
            return False
        if not to_hex.is_land:
            return False

        unit_type = from_hex.unit
        power = unit_power(unit_type)

        # Find the territory this unit belongs to
        source_territory = None
        for t in self.territories:
            if t.owner == player_id and t.contains(from_hex):
                source_territory = t
                break
        if source_territory is None:
            return False

        # Check if target is adjacent to source territory
        territory_hexes = set(h.pos for h in source_territory.hexes)
        is_adjacent = any(
            n.pos == to_hex.pos
            for h in source_territory.hexes
            for n in self.grid.get_neighbors(h)
        ) or to_hex.pos in territory_hexes

        if not is_adjacent and to_hex.pos not in territory_hexes:
            return False

        # Moving within own territory
        if to_hex.owner == player_id and source_territory.contains(to_hex):
            if to_hex.has_combat_unit:
                # Combine
                combined = combine_units(to_hex.unit, unit_type)
                if combined is None:
                    return False
                to_hex.unit = combined
                to_hex.can_move = True
            elif to_hex.has_tree:
                # Chop tree — ends movement
                to_hex.unit = unit_type
                to_hex.can_move = False
            elif to_hex.grave:
                # Clear grave — ends movement
                to_hex.unit = unit_type
                to_hex.can_move = False
                to_hex.grave = False
            elif to_hex.is_empty_land:
                to_hex.unit = unit_type
                to_hex.can_move = True
            else:
                return False

            from_hex.clear_unit()
            return True

        # Attacking enemy/neutral hex
        if to_hex.owner != player_id:
            # Must be adjacent to territory
            neighbor_of_territory = False
            for h in source_territory.hexes:
                if to_hex in self.grid.get_neighbors(h):
                    neighbor_of_territory = True
                    break
            if not neighbor_of_territory:
                return False

            # Check power vs defense
            defense = self.grid.get_relative_power(to_hex)
            if power <= defense:
                return False

            # Capture!
            old_owner = to_hex.owner
            captured_capital = to_hex.has_capital

            # If capturing a capital, zero that territory's gold
            if captured_capital:
                for t in self.territories:
                    if t.owner == old_owner and t.contains(to_hex):
                        t.gold = 0
                        break

            to_hex.owner = player_id
            to_hex.unit = unit_type
            to_hex.has_capital = False  # Captured capitals are destroyed
            to_hex.has_castle = False   # Captured castles are destroyed
            to_hex.grave = False
            to_hex.can_move = False     # Attacking uses the move

            from_hex.clear_unit()

            # Refresh territories (capture may merge ours or split theirs)
            # merge_priority_pos: the attacking unit came from from_hex's
            # territory, so it wins ties when merging same-size territories
            kwargs = {"merge_priority_pos": from_hex.pos}

            if captured_capital:
                attacker_pos = to_hex.pos
                danger_zone = {attacker_pos}
                for n in self.grid.get_neighbors(to_hex):
                    danger_zone.add(n.pos)
                kwargs["capital_avoid"] = {old_owner: danger_zone}

            self.refresh_territories(**kwargs)
            return True

        return False

    # =========================================================
    # State Queries
    # =========================================================

    def get_state_summary(self):
        """Return a dict summary of the game state for AI/logging."""
        return {
            "turn": self.turn_number,
            "current_player": self.current_player_idx,
            "game_over": self.game_over,
            "winner": self.winner,
            "players": [
                {
                    "id": p.id,
                    "alive": p.alive,
                    "territories": len(self.get_player_territories(p.id)),
                    "total_hexes": sum(
                        t.size for t in self.get_player_territories(p.id)
                    ),
                    "total_gold": sum(
                        t.gold for t in self.get_player_territories(p.id)
                    ),
                }
                for p in self.players
            ],
        }

    def clone(self):
        """
        Create a deep copy of the game state for search/simulation.
        This is critical for tree-based AI.
        """
        import copy
        return copy.deepcopy(self)
