# Slay — CLAUDE.md

Recreation of [Slay](https://www.windowsgames.co.uk/slay.html), a turn-based hex strategy game.
Players expand territories, manage per-territory economies, and command units to eliminate opponents.
The primary goal is a clean headless engine suitable for AI self-play and tree-based search.

Reference implementation: [OpenSlay (Java)](https://github.com/jmseren/OpenSlay)

## Tech Stack

- **Python 3** (no type hints, stdlib only except pygame-ce)
- **Pygame-ce** for rendering (renderer module only; engine is headless)
- No external AI/ML libraries — search is hand-rolled

## Project Structure

```
slay/
├── main.py              # Human vs AI game loop (pygame window)
├── arena.py             # Headless AI vs AI match runner with stats
├── engine/              # Headless game engine (zero UI dependencies)
│   ├── game_state.py    # GameState: full state, turns, combat, map gen, clone()
│   ├── actions.py       # Action/ActionType enums, get_legal_actions(), apply_action()
│   ├── hex_grid.py      # HexGrid + Hex: odd-q offset grid, neighbors, flood fill, defense bubbles
│   ├── territory.py     # Territory: economy (income/wages/bankruptcy), capital placement
│   └── units.py         # UnitType enum, stats, wages formula, combine_units()
├── ai/                  # AI player implementations
│   ├── random_ai.py     # Random legal moves (baseline)
│   ├── greedy_ai.py     # 1-ply lookahead with weighted heuristic (uses clone())
│   └── alphabeta_ai.py  # Alpha-beta minimax with apply/undo (no deepcopy), iterative deepening
└── renderer/
    └── hex_renderer.py  # Pygame-ce hex drawing, UI overlay, pixel<->hex coordinate conversion
```

## How to Run

```bash
pip install pygame-ce
python main.py                              # Human (P1) vs GreedyAI (P2)
python arena.py                             # GreedyAI vs RandomAI, 10 seeds, medium map
python arena.py --ai1 alphabeta --ai2 greedy --matches 20 --verbose
python ai/alphabeta_ai.py                   # Standalone alpha-beta benchmark
```

**Controls (main.py):** P=Buy Peasant, C=Buy Castle, Click=Select/Move, E=End Turn, R=New Map, ESC=Quit

## Key Architecture Decisions

- **Headless engine:** `engine/` has zero rendering imports. Can run self-play, AI training,
  and testing without a display. The renderer is a separate layer that reads GameState.
- **GameState.clone():** Uses `copy.deepcopy()` for 1-ply search (GreedyAI). Correct but slow.
- **Apply/undo for deep search:** AlphaBetaAI uses `fast_apply()`/`fast_undo()` operating directly
  on the grid — ~1000x faster than deepcopy. Trades territory/economy accuracy for speed: the
  search model is simplified (adjacent-only moves, no territory recalc, no economy sim). Real
  engine validates and applies the chosen move after search.
- **Action system:** Actions are data objects (`Action` with `ActionType` enum). `get_legal_actions()`
  enumerates all legal moves; `apply_action()` validates and executes. AI picks from legal actions,
  never mutates state directly (except AlphaBetaAI's internal search grid).
- **Territory refresh:** `refresh_territories()` does a full flood-fill recalculation. Called after
  every capture since a single hex flip can merge friendly territories or split enemy ones.
  Handles capital placement with merge priority and avoidance zones.

## Game Mechanics

- **Hex grid:** Odd-q offset coordinates, flat-top hexagons. Map is a single contiguous landmass
  generated via probability-based island generation with cleanup passes.
- **Units:** Peasant (power 1) -> Spearman (2) -> Knight (3) -> Baron (4). Units combine by
  summing power (e.g., Peasant + Peasant = Spearman). Max power is 4.
- **Wages:** `2 * 3^(power-1)` per turn — Peasant=2, Spearman=6, Knight=18, Baron=54.
  Peasant costs 10 gold, Castle costs 15.
- **Economy:** Each territory has its own treasury. Income = land hexes (minus trees/graves).
  Net income = income - wages. Gold < 0 triggers bankruptcy: all units in that territory die.
- **Combat:** Deterministic. Attacker power must strictly exceed the target's "defense bubble"
  (max defense among target hex + all same-owner neighbors). Structures provide defense:
  Capital=1, Castle=2.
- **Trees:** Grow deterministically each turn. Graves become trees. Palms spread on coast
  (1+ adjacent palm), pines spread inland (2+ adjacent pines). Trees block income.
- **Victory:** Last player alive wins. Arena uses hex-count tiebreak at max turns.

## AI System

| AI | Strategy | Speed | Strength |
|----|----------|-------|----------|
| **RandomAI** | Random legal moves (biased away from END_TURN) | Fast | Baseline |
| **GreedyAI** | 1-ply lookahead via `clone()` + weighted eval | Slow (deepcopy) | Moderate |
| **AlphaBetaAI** | Iterative-deepening alpha-beta with apply/undo | Fast (~1M nodes/s) | Strong |

**AlphaBetaAI details:**
- Buy phase runs first via real engine (greedy frontier placement)
- Search uses simplified move gen (adjacent-only captures + repositioning)
- Eval = `my_hexes - opponent_hexes` (simple but directly optimizes win condition)
- Time-budgeted: total turn time split across search calls, with per-search fractions
- Consecutive non-capture move limit (3) prevents oscillation
- Debug mode (`__debug__`) snapshots and verifies grid integrity after search

**Arena** (`arena.py`): Each seed is played twice with sides swapped for fairness.
Reports win rates, elimination vs hex-count decisions, per-side stats.

## Code Conventions

- `Hex.__slots__` and `Action.__slots__` used for memory/speed
- `UnitType` is an `IntEnum` (enables arithmetic: `UnitType(power + 2)`)
- Positions are `(col, row)` tuples throughout
- `h.owner = -1` means neutral/unowned
- `h.can_move` tracks per-unit movement within a turn; reset at turn start
- `h.grave` is a bool on the hex, not a unit type — graves become trees next turn
- Territory index (`territory_idx` in Action) is relative to `get_player_territories()` output,
  which can change after any state mutation (refresh_territories rebuilds the list)
- All AI classes expose `take_turn(game_state) -> int` and `last_turn_log: list[str]`

## Vault Link

Project notes: `C:\Users\Chris.Isaacson\Vault\projects\slay\README.md`
