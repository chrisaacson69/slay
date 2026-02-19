"""
Hex grid system for Slay using odd-q offset coordinates.
Reference: https://www.redblobgames.com/grids/hexagons/

Each hex has:
- (col, row) position
- owner: player index or -1 for unowned
- unit: UnitType on this hex
- has_capital: bool
- has_castle: bool
- grave: bool (dead unit marker, renders as tree)
- can_move: bool (unit hasn't acted this turn)
"""

from .units import UnitType, unit_power, CAPITAL_DEFENSE, CASTLE_DEFENSE


# Neighbor offsets for odd-q hex grid
# Even columns and odd columns have different offsets
NEIGHBOR_DIRS_EVEN = [
    (1, 0), (1, -1), (0, -1),
    (-1, -1), (-1, 0), (0, 1),
]
NEIGHBOR_DIRS_ODD = [
    (1, 1), (1, 0), (0, -1),
    (-1, 0), (-1, 1), (0, 1),
]


class Hex:
    __slots__ = [
        "col", "row", "is_land", "owner", "unit",
        "has_capital", "has_castle", "grave", "can_move",
    ]

    def __init__(self, col, row, is_land=False):
        self.col = col
        self.row = row
        self.is_land = is_land
        self.owner = -1          # -1 = unowned/neutral
        self.unit = UnitType.NONE
        self.has_capital = False
        self.has_castle = False
        self.grave = False
        self.can_move = False

    @property
    def pos(self):
        return (self.col, self.row)

    @property
    def is_empty_land(self):
        """Land with no unit, no tree, no structures."""
        return (self.is_land and self.unit == UnitType.NONE
                and not self.has_capital and not self.has_castle and not self.grave)

    @property
    def has_tree(self):
        return self.unit in (UnitType.TREE_PINE, UnitType.TREE_PALM)

    @property
    def has_combat_unit(self):
        return self.unit in (UnitType.PEASANT, UnitType.SPEARMAN,
                             UnitType.KNIGHT, UnitType.BARON)

    @property
    def defense_power(self):
        """
        The intrinsic defense of this hex (not counting neighbor bubbles).
        Units use their combat power.
        Capitals defend at 2, castles at 3.
        """
        power = unit_power(self.unit)
        if self.has_capital:
            power = max(power, CAPITAL_DEFENSE)
        if self.has_castle:
            power = max(power, CASTLE_DEFENSE)
        return power

    @property
    def produces_income(self):
        """Trees and graves don't produce income. Everything else on land does."""
        if not self.is_land:
            return False
        if self.has_tree or self.grave:
            return False
        return True

    def clear_unit(self):
        """Remove unit from hex."""
        self.unit = UnitType.NONE
        self.can_move = False

    def kill_unit(self):
        """Unit dies — becomes a grave."""
        if self.has_combat_unit:
            self.unit = UnitType.NONE
            self.grave = True
            self.can_move = False

    def __repr__(self):
        return f"Hex({self.col},{self.row} land={self.is_land} owner={self.owner} unit={self.unit.name})"


class HexGrid:
    def __init__(self, width, height):
        self.width = width
        self.height = height
        self.hexes = {}
        for col in range(width):
            for row in range(height):
                self.hexes[(col, row)] = Hex(col, row)

    def get(self, col, row):
        """Get hex at position, or None if out of bounds."""
        return self.hexes.get((col, row))

    def get_neighbors(self, h):
        """Return list of adjacent Hex objects."""
        dirs = NEIGHBOR_DIRS_ODD if h.col % 2 == 1 else NEIGHBOR_DIRS_EVEN
        neighbors = []
        for dc, dr in dirs:
            nc, nr = h.col + dc, h.row + dr
            n = self.hexes.get((nc, nr))
            if n is not None:
                neighbors.append(n)
        return neighbors

    def get_relative_power(self, h):
        """
        Defense bubble: the max of this hex's defense and all
        same-owner neighbors' defense power.
        """
        power = h.defense_power
        for n in self.get_neighbors(h):
            if n.owner == h.owner:
                power = max(power, n.defense_power)
        return power

    def is_coastal(self, h):
        """True if hex has fewer than 6 land neighbors."""
        land_neighbors = sum(1 for n in self.get_neighbors(h) if n.is_land)
        return land_neighbors < 6

    def all_land(self):
        """Return all land hexes."""
        return [h for h in self.hexes.values() if h.is_land]

    def flood_fill(self, start, owner):
        """
        BFS flood fill from start hex, collecting all connected
        hexes with the same owner. Returns list of Hex.
        """
        if not start.is_land or start.owner != owner:
            return []

        visited = set()
        queue = [start]
        visited.add(start.pos)
        result = []

        while queue:
            current = queue.pop(0)
            result.append(current)
            for n in self.get_neighbors(current):
                if n.pos not in visited and n.is_land and n.owner == owner:
                    visited.add(n.pos)
                    queue.append(n)

        return result

    def load_map(self, data, width=None, height=None):
        """
        Load map from a 2D list of integers.
        0 = water, 1+ = land (values 2,3 can indicate trees).
        """
        if width and height:
            self.width = width
            self.height = height
            self.hexes = {}
            for col in range(width):
                for row in range(height):
                    self.hexes[(col, row)] = Hex(col, row)

        for row_idx, row_data in enumerate(data):
            for col_idx, val in enumerate(row_data):
                h = self.get(col_idx, row_idx)
                if h is None:
                    continue
                if val == 0:
                    h.is_land = False
                elif val == 1:
                    h.is_land = True
                elif val == 2:
                    h.is_land = True
                    h.unit = UnitType.TREE_PINE
                elif val == 3:
                    h.is_land = True
                    h.unit = UnitType.TREE_PALM

    def __repr__(self):
        return f"HexGrid({self.width}x{self.height}, {sum(1 for h in self.hexes.values() if h.is_land)} land)"
