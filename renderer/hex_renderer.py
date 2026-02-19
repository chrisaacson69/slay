"""
Hex grid renderer for Slay using pygame-ce.

Flat-top hexagons with odd-q offset coordinates.
Handles: drawing the grid, units, structures, territory borders,
         hover highlights, and coordinate picking (pixel -> hex).
"""

import math
import pygame
from engine.units import UnitType
from engine.hex_grid import Hex


# Player colors (up to 6 players)
PLAYER_COLORS = [
    (100, 160, 255),   # Blue
    (255, 100, 100),   # Red
    (100, 220, 100),   # Green
    (255, 200, 60),    # Yellow
    (200, 120, 255),   # Purple
    (255, 160, 80),    # Orange
]

# Darkened versions for territory borders
PLAYER_BORDER_COLORS = [
    (60, 100, 180),
    (180, 60, 60),
    (60, 150, 60),
    (180, 140, 30),
    (140, 70, 180),
    (180, 100, 40),
]

WATER_COLOR = (30, 60, 120)
UNOWNED_LAND = (160, 160, 160)  # Grey — stands in for missing players
GRID_LINE_COLOR = (0, 0, 0, 60)
HOVER_COLOR = (255, 255, 255, 80)
SELECTED_COLOR = (255, 255, 0, 120)
BG_COLOR = (20, 40, 80)

# Unit display characters
UNIT_CHARS = {
    UnitType.PEASANT: "P",
    UnitType.SPEARMAN: "S",
    UnitType.KNIGHT: "K",
    UnitType.BARON: "B",
    UnitType.TREE_PINE: "^",
    UnitType.TREE_PALM: "Y",
}

# Distinct colors per combat unit — high contrast
UNIT_COLORS = {
    UnitType.PEASANT: (255, 255, 255),    # White
    UnitType.SPEARMAN: (255, 255, 50),    # Bright yellow
    UnitType.KNIGHT: (255, 120, 0),       # Orange
    UnitType.BARON: (255, 50, 50),        # Red
    UnitType.TREE_PINE: (30, 100, 30),
    UnitType.TREE_PALM: (30, 120, 50),
}

# Circle radius scales with unit power
UNIT_RADIUS = {
    UnitType.PEASANT: 0.28,
    UnitType.SPEARMAN: 0.32,
    UnitType.KNIGHT: 0.36,
    UnitType.BARON: 0.40,
}


class HexRenderer:
    def __init__(self, hex_size=28, offset_x=40, offset_y=40):
        self.hex_size = hex_size
        self.offset_x = offset_x
        self.offset_y = offset_y
        self.font = None
        self.small_font = None
        self.unit_font = None
        self._hex_points_cache = {}

    def init_fonts(self):
        """Initialize fonts (must be called after pygame.init)."""
        self.font = pygame.font.SysFont("consolas", 14)
        self.small_font = pygame.font.SysFont("consolas", 10)
        self.unit_font = pygame.font.SysFont("consolas", int(self.hex_size * 0.7), bold=True)

    def hex_to_pixel(self, col, row):
        """Convert hex (col, row) to pixel center (x, y). Flat-top odd-q."""
        x = self.hex_size * 1.5 * col
        y = self.hex_size * math.sqrt(3) * (row + 0.5 * (col % 2))
        return x + self.offset_x, y + self.offset_y

    def pixel_to_hex(self, px, py):
        """Convert pixel (x, y) to hex (col, row). Approximate."""
        # Reverse the flat-top odd-q transform
        x = px - self.offset_x
        y = py - self.offset_y
        col = x / (self.hex_size * 1.5)
        col_round = round(col)
        row = y / (self.hex_size * math.sqrt(3)) - 0.5 * (col_round % 2)
        row_round = round(row)
        return int(col_round), int(row_round)

    def hex_corners(self, cx, cy):
        """Get the 6 corner points of a flat-top hex centered at (cx, cy)."""
        key = (round(cx, 1), round(cy, 1))
        if key in self._hex_points_cache:
            return self._hex_points_cache[key]
        points = []
        for i in range(6):
            angle = math.radians(60 * i)
            px = cx + self.hex_size * math.cos(angle)
            py = cy + self.hex_size * math.sin(angle)
            points.append((px, py))
        self._hex_points_cache[key] = points
        return points

    def draw_hex(self, surface, h, hover_pos=None, selected_pos=None):
        """Draw a single hex tile."""
        cx, cy = self.hex_to_pixel(h.col, h.row)
        corners = self.hex_corners(cx, cy)

        # Fill color
        if not h.is_land:
            return  # Don't draw water hexes (background shows through)

        if h.owner >= 0 and h.owner < len(PLAYER_COLORS):
            color = PLAYER_COLORS[h.owner]
        else:
            color = UNOWNED_LAND

        # Brighten if grave
        if h.grave:
            color = tuple(min(255, c + 30) for c in color)

        pygame.draw.polygon(surface, color, corners)

        # Territory border: draw edges where neighbor is different owner
        # (handled separately in draw_borders for efficiency)

        # Hover highlight
        if hover_pos and h.pos == hover_pos:
            overlay = pygame.Surface((self.hex_size * 2 + 2, self.hex_size * 2 + 2), pygame.SRCALPHA)
            shifted = [(p[0] - cx + self.hex_size + 1, p[1] - cy + self.hex_size + 1) for p in corners]
            pygame.draw.polygon(overlay, HOVER_COLOR, shifted)
            surface.blit(overlay, (cx - self.hex_size - 1, cy - self.hex_size - 1))

        # Selected highlight
        if selected_pos and h.pos == selected_pos:
            overlay = pygame.Surface((self.hex_size * 2 + 2, self.hex_size * 2 + 2), pygame.SRCALPHA)
            shifted = [(p[0] - cx + self.hex_size + 1, p[1] - cy + self.hex_size + 1) for p in corners]
            pygame.draw.polygon(overlay, SELECTED_COLOR, shifted)
            surface.blit(overlay, (cx - self.hex_size - 1, cy - self.hex_size - 1))

        # Draw structures
        if h.has_capital:
            self._draw_capital(surface, cx, cy)
        if h.has_castle:
            self._draw_castle(surface, cx, cy)

        # Draw unit
        if h.unit != UnitType.NONE:
            self._draw_unit(surface, cx, cy, h)

        # Draw grave marker
        if h.grave and h.unit == UnitType.NONE:
            self._draw_grave(surface, cx, cy)

    def _draw_unit(self, surface, cx, cy, h):
        """Draw a unit on the hex — visually distinct per type."""
        char = UNIT_CHARS.get(h.unit)
        if not char or not self.unit_font:
            return
        color = UNIT_COLORS.get(h.unit, (255, 255, 255))

        # Trees are darker and don't need background circles
        if h.has_tree:
            text = self.unit_font.render(char, True, color)
            rect = text.get_rect(center=(cx, cy))
            surface.blit(text, rect)
            return

        # Combat units: sized/colored circle + letter + power number
        radius_frac = UNIT_RADIUS.get(h.unit, 0.3)
        radius = int(self.hex_size * radius_frac)

        # Filled circle background
        pygame.draw.circle(surface, (30, 30, 30), (int(cx), int(cy)), radius)
        # Colored ring — thicker for stronger units
        ring_width = 2 if h.unit == UnitType.PEASANT else 3
        pygame.draw.circle(surface, color, (int(cx), int(cy)), radius, ring_width)

        # Unit letter
        text = self.unit_font.render(char, True, color)
        rect = text.get_rect(center=(cx, cy - 1))
        surface.blit(text, rect)

        # Power number in bottom-right of circle
        if self.small_font:
            from engine.units import unit_power
            power = unit_power(h.unit)
            ptext = self.small_font.render(str(power), True, color)
            surface.blit(ptext, (int(cx + radius * 0.3), int(cy + radius * 0.1)))

        # Movement indicator (small green dot if can move)
        if h.can_move and h.has_combat_unit:
            pygame.draw.circle(surface, (0, 255, 0), (int(cx + radius - 2), int(cy - radius + 2)), 3)

    def _draw_capital(self, surface, cx, cy):
        """Draw a capital marker (small house shape)."""
        s = self.hex_size * 0.2
        points = [
            (cx, cy - s * 1.5),      # top
            (cx - s, cy - s * 0.5),   # left
            (cx - s, cy + s),         # bottom-left
            (cx + s, cy + s),         # bottom-right
            (cx + s, cy - s * 0.5),   # right
        ]
        pygame.draw.polygon(surface, (220, 200, 60), points)
        pygame.draw.polygon(surface, (120, 100, 20), points, 1)

    def _draw_castle(self, surface, cx, cy):
        """Draw a castle marker (small tower)."""
        s = self.hex_size * 0.2
        # Tower body
        body = pygame.Rect(cx - s, cy - s, s * 2, s * 2)
        pygame.draw.rect(surface, (160, 160, 160), body)
        # Battlements
        b = s * 0.4
        for i in range(3):
            bx = cx - s + i * s
            pygame.draw.rect(surface, (160, 160, 160), (bx, cy - s - b, b, b))
        pygame.draw.rect(surface, (80, 80, 80), body, 1)

    def _draw_grave(self, surface, cx, cy):
        """Draw a grave marker (small cross)."""
        s = int(self.hex_size * 0.15)
        color = (100, 80, 60)
        pygame.draw.line(surface, color, (cx, cy - s), (cx, cy + s), 2)
        pygame.draw.line(surface, color, (cx - s//2, cy - s//3), (cx + s//2, cy - s//3), 2)

    def draw_borders(self, surface, grid):
        """Draw territory borders between hexes of different owners."""
        for h in grid.all_land():
            if h.owner < 0:
                continue
            cx, cy = self.hex_to_pixel(h.col, h.row)
            corners = self.hex_corners(cx, cy)

            border_color = PLAYER_BORDER_COLORS[h.owner % len(PLAYER_BORDER_COLORS)]

            neighbors = grid.get_neighbors(h)
            # For each edge direction, check if the neighbor is different
            # Flat-top hex edges correspond to neighbor directions
            dirs_even = [(1, 0), (1, -1), (0, -1), (-1, -1), (-1, 0), (0, 1)]
            dirs_odd = [(1, 1), (1, 0), (0, -1), (-1, 0), (-1, 1), (0, 1)]
            dirs = dirs_odd if h.col % 2 == 1 else dirs_even

            for i, (dc, dr) in enumerate(dirs):
                nc, nr = h.col + dc, h.row + dr
                neighbor = grid.get(nc, nr)
                if neighbor is None or not neighbor.is_land or neighbor.owner != h.owner:
                    # Draw this edge as a border
                    p1 = corners[i]
                    p2 = corners[(i + 1) % 6]
                    pygame.draw.line(surface, border_color, p1, p2, 2)

    def draw_grid(self, surface, grid, hover_pos=None, selected_pos=None):
        """Draw the full hex grid."""
        for h in grid.hexes.values():
            if h.is_land:
                self.draw_hex(surface, h, hover_pos, selected_pos)
        self.draw_borders(surface, grid)

    def draw_ui(self, surface, game_state, screen_width, screen_height,
                selected_territory=None):
        """Draw the UI overlay (current player, gold, turn info)."""
        if not self.font:
            return

        player = game_state.current_player
        territories = game_state.get_player_territories(player.id)
        total_gold = sum(t.gold for t in territories)
        total_income = sum(t.net_income for t in territories)
        total_hexes = sum(t.size for t in territories)

        color = PLAYER_COLORS[player.id % len(PLAYER_COLORS)]

        # Top bar — player overview
        bar_rect = pygame.Rect(0, 0, screen_width, 30)
        pygame.draw.rect(surface, (20, 20, 20), bar_rect)

        info = (f"Player {player.id + 1}  |  "
                f"Turn {game_state.turn_number}  |  "
                f"Territories: {len(territories)}  |  "
                f"Hexes: {total_hexes}  |  "
                f"Gold: {total_gold}  |  "
                f"Income: {total_income:+d}")

        text = self.font.render(info, True, color)
        surface.blit(text, (10, 7))

        # Second bar — selected territory details
        if selected_territory:
            t = selected_territory
            bar2 = pygame.Rect(0, 30, screen_width, 24)
            pygame.draw.rect(surface, (30, 30, 30), bar2)
            t_color = PLAYER_COLORS[t.owner % len(PLAYER_COLORS)] if t.owner >= 0 else (160, 160, 160)
            t_info = (f"Territory: {t.size} hexes  |  "
                      f"Gold: {t.gold}  |  "
                      f"Income: {t.income}  |  "
                      f"Wages: {t.wages}  |  "
                      f"Net: {t.net_income:+d}  |  "
                      f"Units: {len(t.combat_units)}")
            text2 = self.font.render(t_info, True, t_color)
            surface.blit(text2, (10, 33))

        # Bottom bar with controls
        bot_rect = pygame.Rect(0, screen_height - 25, screen_width, 25)
        pygame.draw.rect(surface, (20, 20, 20), bot_rect)
        controls = "P: Buy Peasant  |  C: Buy Castle  |  E: End Turn  |  R: New Map  |  ESC: Quit"
        text = self.small_font.render(controls, True, (160, 160, 160))
        surface.blit(text, (10, screen_height - 20))

    def draw_action_feedback(self, surface, message, screen_width):
        """Draw a temporary action message."""
        if not message or not self.font:
            return
        text = self.font.render(message, True, (255, 255, 100))
        rect = text.get_rect(center=(screen_width // 2, 50))
        bg = rect.inflate(20, 6)
        pygame.draw.rect(surface, (40, 40, 40), bg)
        surface.blit(text, rect)

    def get_screen_size(self, grid):
        """Calculate needed screen size for the grid."""
        max_x, max_y = 0, 0
        for h in grid.hexes.values():
            px, py = self.hex_to_pixel(h.col, h.row)
            max_x = max(max_x, px)
            max_y = max(max_y, py)
        return int(max_x + self.offset_x + self.hex_size), int(max_y + self.offset_y + self.hex_size + 30)
