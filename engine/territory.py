"""
Territory system for Slay.

A territory is a connected group of hexes owned by the same player.
Each territory has:
- A capital (auto-placed in territories of size 2+)
- A gold treasury
- Income = hex count (excluding trees) - unit wages
- If gold goes negative, all units die (bankruptcy)
"""

from .units import UnitType, unit_wage, unit_power


class Territory:
    def __init__(self, hexes, owner):
        self.hexes = list(hexes)
        self.owner = owner
        self.gold = 0
        self._capital_hex = None

    @property
    def size(self):
        return len(self.hexes)

    @property
    def capital_hex(self):
        """Find the hex with the capital, if any."""
        if self._capital_hex and self._capital_hex in self.hexes:
            return self._capital_hex
        for h in self.hexes:
            if h.has_capital:
                self._capital_hex = h
                return h
        return None

    @property
    def income(self):
        """Gross income: count of hexes that produce income."""
        return sum(1 for h in self.hexes if h.produces_income)

    @property
    def wages(self):
        """Total wages for all combat units in this territory."""
        total = 0
        for h in self.hexes:
            total += unit_wage(h.unit)
        return total

    @property
    def net_income(self):
        """Income minus wages. Can be negative."""
        return self.income - self.wages

    @property
    def combat_units(self):
        """List of hexes with combat units."""
        return [h for h in self.hexes if h.has_combat_unit]

    @property
    def movable_units(self):
        """List of hexes with units that can still move this turn."""
        return [h for h in self.hexes if h.has_combat_unit and h.can_move]

    def contains(self, h):
        """Check if a hex is part of this territory."""
        return h in self.hexes

    def neighboring_hexes(self, grid):
        """
        All hexes adjacent to this territory but NOT part of it.
        These are potential attack targets or expansion points.
        """
        hex_set = set(h.pos for h in self.hexes)
        neighbors = set()
        for h in self.hexes:
            for n in grid.get_neighbors(h):
                if n.pos not in hex_set and n.is_land:
                    neighbors.add(n)
        return list(neighbors)

    def enemy_neighbors(self, grid):
        """Adjacent hexes owned by other players."""
        return [h for h in self.neighboring_hexes(grid)
                if h.owner != self.owner and h.owner >= 0]

    def neutral_neighbors(self, grid):
        """Adjacent hexes that are unowned."""
        return [h for h in self.neighboring_hexes(grid)
                if h.owner < 0]

    def collect_income(self):
        """
        Add net income to treasury. If gold goes negative,
        all combat units die (bankruptcy). Returns True if bankrupt.
        """
        self.gold += self.net_income
        if self.gold < 0:
            self._go_bankrupt()
            return True
        return False

    def _go_bankrupt(self):
        """All combat units die, gold resets to 0."""
        for h in self.hexes:
            h.kill_unit()
        self.gold = 0

    def ensure_capital(self, avoid_adjacent_to=None, preferred_pos=None):
        """
        Territories of size 2+ MUST have a capital. If no empty hex
        exists, destroy a castle first, then the highest-power unit.

        preferred_pos: (col, row) — place capital here if possible
            (used when merging: largest old territory's capital wins).
        avoid_adjacent_to: set of (col, row) positions — prefer placing
            away from these. Falls back to adjacent if nothing else.
        """
        if self.size >= 2:
            if self.capital_hex is None:
                # If we have a preferred position (merge), use it
                if preferred_pos:
                    for h in self.hexes:
                        if h.pos == preferred_pos:
                            self._place_capital(h)
                            return

                # 1. Try empty hexes (no unit, no castle)
                candidates = [
                    h for h in self.hexes
                    if not h.has_combat_unit and not h.has_castle
                    and not h.has_tree
                ]

                if candidates:
                    # Prefer away from attacker
                    if avoid_adjacent_to:
                        safe = [h for h in candidates
                                if h.pos not in avoid_adjacent_to]
                        if safe:
                            candidates = safe
                    self._place_capital(candidates[0])
                    return

                # 2. No empty hex — destroy a castle
                castles = [h for h in self.hexes if h.has_castle]
                if castles:
                    h = castles[0]
                    h.has_castle = False
                    self._place_capital(h)
                    return

                # 3. No castles — destroy highest-power unit
                units = [h for h in self.hexes if h.has_combat_unit]
                if units:
                    units.sort(key=lambda h: unit_power(h.unit), reverse=True)
                    h = units[0]
                    h.unit = UnitType.NONE
                    h.grave = True
                    h.can_move = False
                    self._place_capital(h)
                    return

                # 4. Absolute fallback (trees etc) — clear and place
                h = self.hexes[0]
                h.unit = UnitType.NONE
                self._place_capital(h)
        else:
            # Remove capital from tiny territories
            for h in self.hexes:
                h.has_capital = False
            self._capital_hex = None

    def _place_capital(self, h):
        """Place the capital on hex h."""
        h.has_capital = True
        h.grave = False
        self._capital_hex = h

    def can_afford_peasant(self):
        """Can this territory afford to buy a peasant (10 gold)?"""
        from .units import PEASANT_COST
        return self.gold >= PEASANT_COST

    def can_afford_castle(self):
        """Can this territory afford a castle (15 gold)?"""
        from .units import CASTLE_COST
        return self.gold >= CASTLE_COST

    def __repr__(self):
        return (f"Territory(owner={self.owner}, size={self.size}, "
                f"gold={self.gold}, income={self.net_income})")
