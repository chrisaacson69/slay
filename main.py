"""
Slay — Main game loop with pygame-ce rendering.

Controls:
  Left Click  - Select a hex (click unit then target to move)
  P           - Buy peasant mode (click target hex)
  C           - Buy castle mode (click target hex)
  E           - End turn
  R           - Generate new random map
  ESC         - Quit
"""

import sys
import pygame
from engine import GameState
from engine.actions import get_legal_actions, apply_action, Action, ActionType
from engine.units import UnitType
from renderer import HexRenderer
from ai import GreedyAI


class Game:
    def __init__(self):
        pygame.init()

        self.renderer = HexRenderer(hex_size=28)
        self.renderer.init_fonts()

        self.game_state = GameState(num_players=2)
        self.ai = GreedyAI(player_id=1)  # Player 2 is AI

        self.new_map()

        self.selected_hex = None       # (col, row) of selected unit
        self.hover_hex = None          # (col, row) under mouse
        self.selected_territory = None # Territory under cursor/click
        self.mode = "select"           # select, buy_peasant, buy_castle
        self.message = ""
        self.message_timer = 0

        self.clock = pygame.time.Clock()
        self.running = True

    def new_map(self, seed=None):
        """Generate a new map and reset state."""
        import random
        if seed is None:
            seed = random.randint(0, 999999)
        self.game_state = GameState(num_players=2)
        self.game_state.setup_random_map(seed=seed)
        self.game_state.start_turn()

        # Resize window to fit map
        w, h = self.renderer.get_screen_size(self.game_state.grid)
        w = max(w, 600)
        h = max(h, 400)
        self.screen = pygame.display.set_mode((w, h))
        pygame.display.set_caption(f"Slay (seed={seed})")
        self.screen_w, self.screen_h = w, h

        self.selected_hex = None
        self.selected_territory = None
        self.mode = "select"
        self.show_message(f"New map (seed={seed})")

    def show_message(self, msg, duration=120):
        self.message = msg
        self.message_timer = duration

    def find_territory_for_hex(self, pos):
        """Find which territory index a hex belongs to for the current player."""
        player_id = self.game_state.current_player.id
        territories = self.game_state.get_player_territories(player_id)
        for i, t in enumerate(territories):
            for h in t.hexes:
                if h.pos == pos:
                    return i
        return None

    def find_territory_at(self, pos):
        """Find the Territory object at a given hex position."""
        for t in self.game_state.territories:
            for h in t.hexes:
                if h.pos == pos:
                    return t
        return None

    def handle_click(self, pos):
        """Handle a mouse click on a hex."""
        col, row = pos
        h = self.game_state.grid.get(col, row)
        if h is None or not h.is_land:
            self.selected_hex = None
            self.mode = "select"
            return

        gs = self.game_state
        player_id = gs.current_player.id

        if self.mode == "buy_peasant":
            t_idx = self.find_territory_for_hex(h.pos)
            if t_idx is not None:
                action = Action(ActionType.BUY_PEASANT, to_pos=h.pos, territory_idx=t_idx)
                legal = get_legal_actions(gs)
                if action in legal:
                    apply_action(gs, action)
                    self.show_message(f"Bought peasant at {h.pos}")
                else:
                    self.show_message("Can't place peasant there")
            else:
                self.show_message("Not your territory")
            self.mode = "select"
            self.selected_hex = None
            return

        if self.mode == "buy_castle":
            t_idx = self.find_territory_for_hex(h.pos)
            if t_idx is not None:
                action = Action(ActionType.BUY_CASTLE, to_pos=h.pos, territory_idx=t_idx)
                legal = get_legal_actions(gs)
                if action in legal:
                    apply_action(gs, action)
                    self.show_message(f"Built castle at {h.pos}")
                else:
                    self.show_message("Can't place castle there")
            else:
                self.show_message("Not your territory")
            self.mode = "select"
            self.selected_hex = None
            return

        # Select mode
        if self.selected_hex is not None:
            # Try to move selected unit to clicked hex
            action = Action(ActionType.MOVE_UNIT, from_pos=self.selected_hex, to_pos=h.pos)
            legal = get_legal_actions(gs)
            if action in legal:
                apply_action(gs, action)
                self.show_message(f"Moved {self.selected_hex} -> {h.pos}")
                self.selected_hex = None
            elif h.owner == player_id and h.has_combat_unit and h.can_move:
                # Select the new unit instead
                self.selected_hex = h.pos
                self.show_message(f"Selected unit at {h.pos}")
            else:
                self.show_message("Invalid move")
                self.selected_hex = None
        else:
            # Select a unit
            if h.owner == player_id and h.has_combat_unit and h.can_move:
                self.selected_hex = h.pos
                self.show_message(f"Selected unit at {h.pos}")
            elif h.owner == player_id:
                self.show_message("No movable unit there")
            else:
                self.show_message("Not your hex")

    def run(self):
        """Main game loop."""
        while self.running:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    self.running = False

                elif event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE:
                        self.running = False
                    elif event.key == pygame.K_e:
                        apply_action(self.game_state, Action(ActionType.END_TURN))
                        self.selected_hex = None
                        self.mode = "select"
                        # Let AI take its turn
                        if (not self.game_state.game_over
                                and self.game_state.current_player.id == self.ai.player_id):
                            n = self.ai.take_turn(self.game_state)
                            # Print AI actions to console for debugging
                            print(f"--- AI Turn ({n} actions) ---")
                            for entry in self.ai.last_turn_log:
                                print(f"  {entry}")
                            self.show_message(f"AI took {n} actions. Your turn!")
                        else:
                            p = self.game_state.current_player
                            self.show_message(f"Player {p.id + 1}'s turn")
                        if self.game_state.game_over:
                            w = self.game_state.winner
                            self.show_message(f"Game Over! Player {w + 1} wins!", 300)
                    elif event.key == pygame.K_p:
                        self.mode = "buy_peasant"
                        self.selected_hex = None
                        self.show_message("Buy Peasant — click target hex")
                    elif event.key == pygame.K_c:
                        self.mode = "buy_castle"
                        self.selected_hex = None
                        self.show_message("Buy Castle — click target hex")
                    elif event.key == pygame.K_r:
                        self.new_map()

                elif event.type == pygame.MOUSEBUTTONDOWN:
                    if event.button == 1:  # Left click
                        mx, my = event.pos
                        hex_pos = self.renderer.pixel_to_hex(mx, my)
                        self.handle_click(hex_pos)
                    elif event.button == 3:  # Right click = cancel
                        self.selected_hex = None
                        self.mode = "select"
                        self.show_message("")

            # Update hover and territory selection
            mx, my = pygame.mouse.get_pos()
            self.hover_hex = self.renderer.pixel_to_hex(mx, my)
            self.selected_territory = self.find_territory_at(self.hover_hex)

            # Draw
            self.screen.fill((20, 40, 80))
            self.renderer.draw_grid(
                self.screen,
                self.game_state.grid,
                hover_pos=self.hover_hex,
                selected_pos=self.selected_hex,
            )
            self.renderer.draw_ui(
                self.screen, self.game_state,
                self.screen_w, self.screen_h,
                selected_territory=self.selected_territory,
            )

            # Action message
            if self.message_timer > 0:
                self.renderer.draw_action_feedback(self.screen, self.message, self.screen_w)
                self.message_timer -= 1

            pygame.display.flip()
            self.clock.tick(60)

        pygame.quit()


if __name__ == "__main__":
    game = Game()
    game.run()
