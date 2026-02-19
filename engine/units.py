"""
Unit types and their stats for Slay.
Wages follow the formula: 2 * 3^(power-1)
  Peasant=2, Spearman=6, Knight=18, Baron=54

Purchase cost: 10 gold for a peasant, 15 for a castle/fort.
Units combine: peasant + peasant = spearman, etc.
Max power is 4 (Baron). Cannot combine beyond that.
"""

from enum import IntEnum


class UnitType(IntEnum):
    NONE = 0
    TREE_PINE = 1
    TREE_PALM = 2
    PEASANT = 3      # power 1, wage 2
    SPEARMAN = 4     # power 2, wage 6
    KNIGHT = 5       # power 3, wage 18
    BARON = 6        # power 4, wage 54


# Stats indexed by UnitType
UNIT_STATS = {
    UnitType.PEASANT:  {"power": 1, "wage": 2},
    UnitType.SPEARMAN: {"power": 2, "wage": 6},
    UnitType.KNIGHT:   {"power": 3, "wage": 18},
    UnitType.BARON:    {"power": 4, "wage": 54},
}

PEASANT_COST = 10
CASTLE_COST = 15

# Defense values for structures
CAPITAL_DEFENSE = 1
CASTLE_DEFENSE = 2


def unit_power(unit_type):
    """Get the combat power of a unit type."""
    if unit_type in UNIT_STATS:
        return UNIT_STATS[unit_type]["power"]
    return 0


def unit_wage(unit_type):
    """Get the per-turn wage cost of a unit type."""
    if unit_type in UNIT_STATS:
        return UNIT_STATS[unit_type]["wage"]
    return 0


def combine_units(type_a, type_b):
    """
    Combine two unit types. Returns the resulting type, or None if invalid.
    Combination adds power levels: peasant(1) + peasant(1) = spearman(2), etc.
    Max power is 4 (Baron).
    """
    power_a = unit_power(type_a)
    power_b = unit_power(type_b)
    if power_a == 0 or power_b == 0:
        return None
    combined_power = power_a + power_b
    if combined_power > 4:
        return None
    # Map power back to unit type
    return UnitType(combined_power + 2)  # power 1 = type 3 (PEASANT), etc.


def unit_from_power(power):
    """Get UnitType from a power level (1-4)."""
    if 1 <= power <= 4:
        return UnitType(power + 2)
    return None
