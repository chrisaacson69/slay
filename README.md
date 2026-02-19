# Slay

> Hex-based strategy game recreation with AI player development.

**Status:** active
**Created:** 2026-02-12
**Vault:** `C:\Users\Chris.Isaacson\Vault\projects\slay\README.md`

## Overview

Recreation of [Slay](https://www.windowsgames.co.uk/slay.html), a turn-based hex strategy game where players expand territories, manage economies, and command units to eliminate opponents. The goal is a clean headless engine suitable for AI self-play and tree-based search.

Reference: [OpenSlay (Java)](https://github.com/jmseren/OpenSlay) — ~65-70% complete recreation, used for rules reference.

## Architecture

```
slay/
├── engine/          # Headless game engine (no UI dependency)
│   ├── units.py     # Unit types, stats, combination logic
│   ├── hex_grid.py  # Odd-q offset hex grid, neighbors, flood fill
│   ├── territory.py # Territory economy: income, wages, bankruptcy
│   ├── game_state.py# Full state, turns, combat, map generation
│   └── actions.py   # Legal action enumeration + application
├── renderer/        # Pygame-ce visualization
│   └── hex_renderer.py  # Hex drawing, UI overlay, coordinate picking
├── ai/              # AI players
│   └── random_ai.py # Random baseline
└── main.py          # Game loop with human vs AI
```

**Key design**: Engine is fully separated from renderer. The engine can run headless for self-play, AI training, and testing. `GameState.clone()` supports tree-based search.

## Game Mechanics

- **Hex grid**: Odd-q offset coordinates, flat-top hexagons
- **Units**: Peasant (1) → Spearman (2) → Knight (3) → Baron (4). Units combine by adding power
- **Wages**: 2 × 3^(power-1) per turn — Peasant=2, Spearman=6, Knight=18, Baron=54
- **Economy**: Territory income = land hexes (minus trees/graves). Gold < 0 = bankruptcy (all units die)
- **Combat**: Deterministic. Attacker power must exceed defender's "defense bubble" (max power among target + same-owner neighbors)
- **Structures**: Capital (defense 2, auto-placed), Castle (defense 3, costs 15)
- **Victory**: Last player standing

## Running

```bash
pip install pygame-ce
python main.py
```

**Controls**: P=Buy Peasant, C=Buy Castle, Click=Select/Move, E=End Turn, R=New Map

## Roadmap

- [x] Core engine (units, grid, territories, combat, actions)
- [x] Pygame-ce renderer with hex grid display
- [x] Random AI baseline
- [ ] Improve map generation (multi-player, balanced starts)
- [ ] Smarter AI (heuristic, then tree search)
- [ ] Polish renderer (sprites, animations, territory info panel)
- [ ] Headless self-play harness for AI training
- [ ] Performance optimization for deep search

## Tags
python, ai, games
