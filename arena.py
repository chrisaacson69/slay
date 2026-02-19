"""Headless arena for AI vs AI matches.

Usage:
    python arena.py                           # GreedyAI vs RandomAI, 10 seeds, medium map
    python arena.py --matches 50              # more seeds
    python arena.py --ai1 random --ai2 greedy # pick matchup
    python arena.py --seeds 42,99,7           # specific seeds
    python arena.py --verbose                 # per-match details
    python arena.py --map-size large          # full 24x16 map (slow with GreedyAI)

Note: GreedyAI uses deepcopy for 1-ply lookahead, which makes it slow on
larger maps. The default medium (16x12) map keeps games under ~60s each.
Use --map-size small for faster iteration during development.
"""

import argparse
import sys
import time
from collections import namedtuple

from engine import GameState
from ai import RandomAI, GreedyAI, AlphaBetaAI

MAX_TURNS = 50

MAP_SIZES = {
    "small": (12, 8),
    "medium": (16, 12),
    "large": (24, 16),
}

AI_REGISTRY = {
    "random": RandomAI,
    "greedy": GreedyAI,
    "alphabeta": AlphaBetaAI,
}

MatchResult = namedtuple("MatchResult", [
    "seed", "swapped", "winner", "turn_count", "hex_counts", "territory_counts",
    "decided_by",  # "elimination", "hexes", or "draw"
])


def run_match(ai1_cls, ai2_cls, seed, max_turns=MAX_TURNS,
              map_width=16, map_height=12):
    """Run a single match and return a MatchResult.

    ai1_cls is instantiated as player 0, ai2_cls as player 1.
    If the game hits max_turns without elimination, the player
    with more hexes wins (tiebreaker). True draws only when equal.
    """
    gs = GameState(num_players=2)
    gs.setup_random_map(width=map_width, height=map_height, seed=seed)
    gs.start_turn()

    ais = [ai1_cls(0), ai2_cls(1)]

    while not gs.game_over and gs.turn_number < max_turns:
        current_ai = ais[gs.current_player_idx]
        current_ai.take_turn(gs)

    # Collect hex/territory counts
    hex_counts = {}
    territory_counts = {}
    for p in gs.players:
        territories = gs.get_player_territories(p.id)
        territory_counts[p.id] = len(territories)
        hex_counts[p.id] = sum(len(t.hexes) for t in territories)

    # Determine winner
    if gs.game_over and gs.winner is not None:
        winner = gs.winner
        decided_by = "elimination"
    elif hex_counts[0] != hex_counts[1]:
        # Tiebreaker: most hexes wins
        winner = 0 if hex_counts[0] > hex_counts[1] else 1
        decided_by = "hexes"
    else:
        winner = None
        decided_by = "draw"

    return MatchResult(
        seed=seed,
        swapped=False,
        winner=winner,
        turn_count=gs.turn_number,
        hex_counts=hex_counts,
        territory_counts=territory_counts,
        decided_by=decided_by,
    )


def _ai_winner(result):
    """Map a MatchResult's raw winner (player_id) to AI index.

    Returns 0 if ai1 won, 1 if ai2 won, None if draw.
    Accounts for side-swapping.
    """
    if result.winner is None:
        return None
    if not result.swapped:
        return result.winner  # ai1=player0, ai2=player1
    return 1 - result.winner  # ai1=player1, ai2=player0


def _winner_label(result, ai1_name, ai2_name):
    aw = _ai_winner(result)
    if aw is None:
        return "Draw"
    name = ai1_name if aw == 0 else ai2_name
    if result.decided_by == "hexes":
        return f"{name} (by hexes)"
    return name


def run_arena(ai1_cls, ai2_cls, seeds, max_turns=MAX_TURNS,
              map_width=16, map_height=12,
              verbose=False, ai1_name="AI1", ai2_name="AI2"):
    """Run all matches with side-swapping. Returns list of MatchResult.

    Each seed is played twice: once with ai1 as player 0, once swapped.
    """
    results = []
    total = len(seeds) * 2

    for i, seed in enumerate(seeds):
        # Game A: ai1 as player 0, ai2 as player 1
        t0 = time.time()
        result_a = run_match(ai1_cls, ai2_cls, seed, max_turns,
                             map_width, map_height)
        results.append(result_a)
        dt_a = time.time() - t0

        if verbose:
            w = _winner_label(result_a, ai1_name, ai2_name)
            print(f"  [{2*i+1:3d}/{total}] seed={seed:4d}  "
                  f"{ai1_name} vs {ai2_name}  -> {w} "
                  f"in {result_a.turn_count} turns ({dt_a:.1f}s)")
            sys.stdout.flush()

        # Game B: swapped — ai2 as player 0, ai1 as player 1
        t0 = time.time()
        result_b = run_match(ai2_cls, ai1_cls, seed, max_turns,
                             map_width, map_height)
        result_b = result_b._replace(swapped=True)
        results.append(result_b)
        dt_b = time.time() - t0

        if verbose:
            w = _winner_label(result_b, ai1_name, ai2_name)
            print(f"  [{2*i+2:3d}/{total}] seed={seed:4d}  "
                  f"{ai2_name} vs {ai1_name}  -> {w} "
                  f"in {result_b.turn_count} turns ({dt_b:.1f}s)")
            sys.stdout.flush()
        elif total > 2:
            done = 2 * (i + 1)
            print(f"\r  Progress: {done}/{total} games ...", end="")
            sys.stdout.flush()

    if not verbose and total > 2:
        print()  # clear the progress line

    return results


def print_summary(results, ai1_name, ai2_name):
    """Print formatted summary table."""
    total = len(results)
    num_seeds = total // 2

    ai1_wins = sum(1 for r in results if _ai_winner(r) == 0)
    ai2_wins = sum(1 for r in results if _ai_winner(r) == 1)
    draws = sum(1 for r in results if _ai_winner(r) is None)

    # Break down by how the game was decided
    eliminations = sum(1 for r in results if r.decided_by == "elimination")
    hex_wins = sum(1 for r in results if r.decided_by == "hexes")

    # Per-side stats: how does ai1 do as player 0 (first) vs player 1 (second)?
    ai1_as_p0 = [r for r in results if not r.swapped]
    ai1_as_p1 = [r for r in results if r.swapped]
    ai1_wins_as_p0 = sum(1 for r in ai1_as_p0 if _ai_winner(r) == 0)
    ai1_wins_as_p1 = sum(1 for r in ai1_as_p1 if _ai_winner(r) == 0)

    avg_turns = sum(r.turn_count for r in results) / total if total else 0

    # Avg hexes for the winner of each game
    winner_hex_list = []
    for r in results:
        aw = _ai_winner(r)
        if aw is not None:
            pid = aw if not r.swapped else (1 - aw)
            winner_hex_list.append(r.hex_counts[pid])
    avg_winner_hexes = (sum(winner_hex_list) / len(winner_hex_list)
                        if winner_hex_list else 0)

    name_w = max(len(ai1_name), len(ai2_name), 5)

    print()
    print(f"=== {ai1_name} vs {ai2_name} "
          f"({num_seeds} seeds x 2 sides = {total} games) ===")
    print()
    print(f"  {ai1_name:<{name_w}} wins: {ai1_wins:3d} / {total}  "
          f"({100 * ai1_wins / total:.1f}%)")
    print(f"  {ai2_name:<{name_w}} wins: {ai2_wins:3d} / {total}  "
          f"({100 * ai2_wins / total:.1f}%)")
    print(f"  {'Draws':<{name_w}}     : {draws:3d} / {total}")
    print()
    print(f"  Decided by elimination: {eliminations}")
    print(f"  Decided by hex count:   {hex_wins}")
    print()
    print(f"  Avg game length:  {avg_turns:.1f} turns")
    print(f"  Avg winner hexes: {avg_winner_hexes:.1f}")
    print()
    print(f"  {ai1_name} as Player 1 (first):  "
          f"{ai1_wins_as_p0}/{len(ai1_as_p0)} wins")
    print(f"  {ai1_name} as Player 2 (second): "
          f"{ai1_wins_as_p1}/{len(ai1_as_p1)} wins")
    print()


def main():
    parser = argparse.ArgumentParser(
        description="Slay AI Arena - headless AI vs AI matches")
    parser.add_argument("--ai1", default="greedy", choices=AI_REGISTRY.keys(),
                        help="First AI (default: greedy)")
    parser.add_argument("--ai2", default="random", choices=AI_REGISTRY.keys(),
                        help="Second AI (default: random)")
    parser.add_argument("--matches", type=int, default=10,
                        help="Number of seeds to play, each played twice "
                             "for side fairness (default: 10)")
    parser.add_argument("--seeds", type=str, default=None,
                        help="Comma-separated list of specific seeds "
                             "(overrides --matches)")
    parser.add_argument("--max-turns", type=int, default=MAX_TURNS,
                        help=f"Max turns before hex-count tiebreak "
                             f"(default: {MAX_TURNS})")
    parser.add_argument("--map-size", default="medium",
                        choices=MAP_SIZES.keys(),
                        help="Map size preset (default: medium). "
                             "small=12x8, medium=16x12, large=24x16")
    parser.add_argument("--verbose", action="store_true",
                        help="Print per-match details")
    args = parser.parse_args()

    ai1_cls = AI_REGISTRY[args.ai1]
    ai2_cls = AI_REGISTRY[args.ai2]

    ai1_name = args.ai1.capitalize() + "AI"
    ai2_name = args.ai2.capitalize() + "AI"
    if args.ai1 == args.ai2:
        ai1_name += "_A"
        ai2_name += "_B"

    if args.seeds:
        seeds = [int(s.strip()) for s in args.seeds.split(",")]
    else:
        seeds = list(range(args.matches))

    map_w, map_h = MAP_SIZES[args.map_size]
    total_games = len(seeds) * 2
    print(f"Running {ai1_name} vs {ai2_name}: "
          f"{len(seeds)} seeds x 2 sides = {total_games} games "
          f"(map {map_w}x{map_h}, max {args.max_turns} turns)")
    if args.verbose:
        print()
    sys.stdout.flush()

    t0 = time.time()
    results = run_arena(ai1_cls, ai2_cls, seeds, args.max_turns,
                        map_width=map_w, map_height=map_h,
                        verbose=args.verbose,
                        ai1_name=ai1_name, ai2_name=ai2_name)
    elapsed = time.time() - t0

    print_summary(results, ai1_name, ai2_name)
    print(f"  Completed in {elapsed:.1f}s "
          f"({elapsed / len(results):.2f}s per game)")
    print()


if __name__ == "__main__":
    main()
