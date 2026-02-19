"""
Alpha-Beta Minimax AI for Slay.

Uses apply/undo instead of deepcopy for ~1000x faster state evaluation.
Simplified search model: adjacent-only moves, no territory recalculation,
no economy simulation. Real engine validates and applies chosen moves.

Standalone benchmark: python ai/alphabeta_ai.py
"""

import os
import sys
import time

# Allow standalone execution (python ai/alphabeta_ai.py from slay/)
if __name__ == "__main__":
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from engine.actions import ActionType, Action, apply_action
from engine.units import UnitType, unit_power, PEASANT_COST

# ---------------------------------------------------------------------------
# Search action types (lightweight tuples, no objects)
# ---------------------------------------------------------------------------
ACT_CAPTURE = 0
ACT_MOVE = 1
ACT_END_TURN = 2

INF = 100_000

# ---------------------------------------------------------------------------
# Search globals (avoid passing through every recursive call)
# ---------------------------------------------------------------------------
_deadline = 0.0
_timed_out = False


# ---------------------------------------------------------------------------
# Simplified legal-move generation for search
# ---------------------------------------------------------------------------

def get_search_actions(grid, player_id):
    """Generate simplified legal actions for the current player.

    For each owned land hex with a movable combat unit, check 6 neighbors:
      CAPTURE: enemy/neutral hex where unit_power > get_relative_power(target)
      MOVE:    same-owner empty hex (unit repositioning)
    Plus END_TURN (always last for best alpha-beta cutoff ordering).

    Returns list of (action_type, from_pos, to_pos) tuples.
    """
    captures = []
    moves = []

    for h in grid.hexes.values():
        if not h.is_land or h.owner != player_id:
            continue
        if not h.has_combat_unit or not h.can_move:
            continue

        power = unit_power(h.unit)
        fpos = h.pos

        for n in grid.get_neighbors(h):
            if not n.is_land:
                continue

            if n.owner != player_id:
                # Enemy or neutral — potential capture
                if power > grid.get_relative_power(n):
                    captures.append((ACT_CAPTURE, fpos, n.pos))
            else:
                # Same-owner empty hex — repositioning
                if (n.unit == UnitType.NONE and not n.has_capital
                        and not n.has_castle and not n.grave):
                    moves.append((ACT_MOVE, fpos, n.pos))

    # Captures first for better pruning, END_TURN last
    return captures + moves + [(ACT_END_TURN, None, None)]


# ---------------------------------------------------------------------------
# Apply / Undo  (in-place, ~1000x faster than deepcopy)
# ---------------------------------------------------------------------------

def fast_apply(grid, player_idx, num_players, action):
    """Apply action in-place. Returns (new_player_idx, undo_tuple)."""
    atype = action[0]

    if atype == ACT_CAPTURE:
        fpos, tpos = action[1], action[2]
        fh = grid.hexes[fpos]
        th = grid.hexes[tpos]

        # Save 8 fields
        undo = (ACT_CAPTURE, fpos, tpos,
                fh.unit, fh.can_move,
                th.owner, th.unit, th.has_capital,
                th.has_castle, th.grave, th.can_move)

        # Capture: move unit, flip owner, destroy structures
        th.owner = fh.owner
        th.unit = fh.unit
        th.has_capital = False
        th.has_castle = False
        th.grave = False
        th.can_move = False

        fh.unit = UnitType.NONE
        fh.can_move = False

        return player_idx, undo

    if atype == ACT_MOVE:
        fpos, tpos = action[1], action[2]
        fh = grid.hexes[fpos]
        th = grid.hexes[tpos]

        # Save 4 fields
        undo = (ACT_MOVE, fpos, tpos,
                fh.unit, fh.can_move, th.unit, th.can_move)

        # Reposition: unit can still act after moving to empty hex
        th.unit = fh.unit
        th.can_move = True

        fh.unit = UnitType.NONE
        fh.can_move = False

        return player_idx, undo

    # ACT_END_TURN — swap player and reset next player's can_move
    nidx = (player_idx + 1) % num_players
    npid = nidx  # player_id == index in this game

    saved = {}
    for pos, h in grid.hexes.items():
        if h.owner == npid and h.has_combat_unit:
            saved[pos] = h.can_move
            h.can_move = True

    return nidx, (ACT_END_TURN, saved)


def fast_undo(grid, undo):
    """Restore grid state from undo tuple."""
    atype = undo[0]

    if atype == ACT_CAPTURE:
        (_, fpos, tpos,
         fu, fcm, tow, tu, tcap, tcas, tgr, tcm) = undo
        fh = grid.hexes[fpos]
        th = grid.hexes[tpos]
        fh.unit = fu
        fh.can_move = fcm
        th.owner = tow
        th.unit = tu
        th.has_capital = tcap
        th.has_castle = tcas
        th.grave = tgr
        th.can_move = tcm

    elif atype == ACT_MOVE:
        _, fpos, tpos, fu, fcm, tu, tcm = undo
        fh = grid.hexes[fpos]
        th = grid.hexes[tpos]
        fh.unit = fu
        fh.can_move = fcm
        th.unit = tu
        th.can_move = tcm

    else:  # ACT_END_TURN
        _, saved = undo
        for pos, cm in saved.items():
            grid.hexes[pos].can_move = cm


# ---------------------------------------------------------------------------
# Evaluation
# ---------------------------------------------------------------------------

def eval_hex_count(grid, player_id):
    """my_hexes - opponent_hexes.  Simple, fast, directly optimizes win cond."""
    my = 0
    opp = 0
    for h in grid.hexes.values():
        if not h.is_land:
            continue
        if h.owner == player_id:
            my += 1
        elif h.owner >= 0:
            opp += 1
    return my - opp


# ---------------------------------------------------------------------------
# Alpha-Beta search
# ---------------------------------------------------------------------------

def alphabeta(grid, pidx, nplayers, max_pid, depth, alpha, beta, stats):
    """Standard alpha-beta.

    Checks whose turn it is at each node (not alternating by depth).
    Max/min switches when END_TURN changes the active player.
    """
    global _timed_out

    stats[0] += 1
    if (stats[0] & 4095) == 0 and time.perf_counter() >= _deadline:
        _timed_out = True
        return 0
    if _timed_out:
        return 0

    if depth <= 0:
        return eval_hex_count(grid, max_pid)

    current_pid = pidx  # player_id == index
    is_max = (current_pid == max_pid)
    actions = get_search_actions(grid, current_pid)

    if is_max:
        value = -INF
        for action in actions:
            nidx, undo = fast_apply(grid, pidx, nplayers, action)
            v = alphabeta(grid, nidx, nplayers, max_pid,
                          depth - 1, alpha, beta, stats)
            fast_undo(grid, undo)
            if _timed_out:
                return 0
            if v > value:
                value = v
            if value > alpha:
                alpha = value
            if alpha >= beta:
                break
        return value
    else:
        value = INF
        for action in actions:
            nidx, undo = fast_apply(grid, pidx, nplayers, action)
            v = alphabeta(grid, nidx, nplayers, max_pid,
                          depth - 1, alpha, beta, stats)
            fast_undo(grid, undo)
            if _timed_out:
                return 0
            if v < value:
                value = v
            if value < beta:
                beta = value
            if alpha >= beta:
                break
        return value


# ---------------------------------------------------------------------------
# Debug helpers (active when __debug__ is True, i.e. no -O flag)
# ---------------------------------------------------------------------------

def _snapshot(grid):
    """Capture grid state for apply/undo correctness verification."""
    return {pos: (h.owner, h.unit, h.has_capital, h.has_castle, h.grave, h.can_move)
            for pos, h in grid.hexes.items()}


def _verify(grid, snap):
    """Assert grid matches a previous snapshot."""
    for pos, vals in snap.items():
        h = grid.hexes[pos]
        actual = (h.owner, h.unit, h.has_capital, h.has_castle, h.grave, h.can_move)
        assert actual == vals, f"Grid mismatch at {pos}: {actual} != {vals}"


# ---------------------------------------------------------------------------
# Search wrappers
# ---------------------------------------------------------------------------

def search_best_action(grid, player_idx, num_players, player_id,
                       max_depth, time_limit):
    """Iterative-deepening alpha-beta. Returns (best_action, depth, stats)."""
    global _deadline, _timed_out

    t0 = time.perf_counter()
    _deadline = t0 + time_limit

    if __debug__:
        snap = _snapshot(grid)

    best_action = (ACT_END_TURN, None, None)
    best_score = -INF
    total_nodes = 0
    depth_reached = 0

    for depth in range(1, max_depth + 1):
        _timed_out = False
        stats = [0]

        actions = get_search_actions(grid, player_id)
        d_best = (ACT_END_TURN, None, None)
        d_score = -INF
        alpha = -INF

        for action in actions:
            nidx, undo = fast_apply(grid, player_idx, num_players, action)
            score = alphabeta(grid, nidx, num_players, player_id,
                              depth - 1, alpha, INF, stats)
            fast_undo(grid, undo)

            if _timed_out:
                break

            if score > d_score:
                d_score = score
                d_best = action
            if score > alpha:
                alpha = score

        total_nodes += stats[0]

        if not _timed_out:
            best_action = d_best
            best_score = d_score
            depth_reached = depth

        if time.perf_counter() >= _deadline:
            break

    if __debug__:
        _verify(grid, snap)

    elapsed = time.perf_counter() - t0
    return best_action, depth_reached, {
        "nodes": total_nodes,
        "elapsed": elapsed,
        "score": best_score,
    }


def search_at_depth(grid, player_idx, num_players, player_id,
                    depth, time_limit):
    """Direct to depth D, no iterative deepening.

    Used after benchmarking establishes the optimal depth.
    Saves ~10% by skipping ID overhead.
    """
    global _deadline, _timed_out

    t0 = time.perf_counter()
    _deadline = t0 + time_limit
    _timed_out = False
    stats = [0]

    if __debug__:
        snap = _snapshot(grid)

    actions = get_search_actions(grid, player_id)
    best_action = (ACT_END_TURN, None, None)
    best_score = -INF
    alpha = -INF

    for action in actions:
        nidx, undo = fast_apply(grid, player_idx, num_players, action)
        score = alphabeta(grid, nidx, num_players, player_id,
                          depth - 1, alpha, INF, stats)
        fast_undo(grid, undo)

        if _timed_out:
            break

        if score > best_score:
            best_score = score
            best_action = action
        if score > alpha:
            alpha = score

    if __debug__:
        _verify(grid, snap)

    elapsed = time.perf_counter() - t0
    return best_action, depth, {
        "nodes": stats[0],
        "elapsed": elapsed,
        "score": best_score,
    }


# ---------------------------------------------------------------------------
# Buy phase (uses real engine, runs before search)
# ---------------------------------------------------------------------------

def _find_buy_target(grid, territory, player_id):
    """Find best hex in territory to place a new peasant.

    Prefers hexes adjacent to enemy territory (frontier placement).
    """
    best = None
    best_enemy_adj = -1

    for h in territory.hexes:
        if not (h.is_empty_land or h.grave or h.has_tree):
            continue
        enemy_adj = 0
        for n in grid.get_neighbors(h):
            if n.is_land and n.owner >= 0 and n.owner != player_id:
                enemy_adj += 1
        if enemy_adj > best_enemy_adj:
            best_enemy_adj = enemy_adj
            best = h

    return best


def _buy_phase(game_state, player_id):
    """Greedily buy peasants via real engine.

    Highest net-income territory first, frontier placement.
    """
    territories = game_state.get_player_territories(player_id)
    territories.sort(key=lambda t: t.net_income, reverse=True)
    bought = 0

    for territory in territories:
        while territory.gold >= PEASANT_COST:
            # Don't buy if it would cause bankruptcy next turn
            # net_income already reflects current wages; -2 for new peasant
            if territory.gold - PEASANT_COST + territory.net_income - 2 < 0:
                break

            target = _find_buy_target(game_state.grid, territory, player_id)
            if target is None:
                break
            if not game_state.buy_peasant(territory, target):
                break
            bought += 1

    return bought


# ---------------------------------------------------------------------------
# AlphaBetaAI class
# ---------------------------------------------------------------------------

def _action_str(action):
    atype, fpos, tpos = action
    if atype == ACT_END_TURN:
        return "END_TURN"
    label = "CAPTURE" if atype == ACT_CAPTURE else "MOVE"
    return f"{label} {fpos}->{tpos}"


class AlphaBetaAI:
    def __init__(self, player_id, time_limit=5.0, max_depth=20):
        self.player_id = player_id
        self.time_limit = time_limit  # total seconds for the ENTIRE turn
        self.max_depth = max_depth
        self.last_turn_log = []

    def take_turn(self, game_state):
        """Execute a full turn: buy phase then search-and-act loop.

        time_limit is a budget for the whole turn, split across search calls.
        """
        self.last_turn_log = []
        pid = self.player_id
        actions_taken = 0
        turn_start = time.perf_counter()

        # --- Buy phase (real engine) ---
        bought = _buy_phase(game_state, pid)
        if bought:
            self.last_turn_log.append(f"Bought {bought} peasants")

        # --- Search-and-act loop ---
        num_players = len(game_state.players)
        max_actions = 50
        consecutive_moves = 0  # non-capture move counter to prevent oscillation

        for i in range(max_actions):
            if game_state.game_over or game_state.current_player.id != pid:
                break

            # Budget remaining time across expected remaining actions
            elapsed = time.perf_counter() - turn_start
            remaining = self.time_limit - elapsed
            if remaining <= 0.05:
                apply_action(game_state, Action(ActionType.END_TURN))
                actions_taken += 1
                break

            # Give each search a fraction of the remaining budget
            per_search = min(remaining, remaining / max(1, 8 - i))

            action, depth, stats = search_best_action(
                game_state.grid, game_state.current_player_idx,
                num_players, pid, self.max_depth, per_search,
            )

            self.last_turn_log.append(
                f"d={depth} n={stats['nodes']} s={stats['score']:+d} "
                f"-> {_action_str(action)}"
            )
            actions_taken += 1

            atype = action[0]

            if atype == ACT_END_TURN:
                apply_action(game_state, Action(ActionType.END_TURN))
                break

            # Limit consecutive non-capture moves to prevent oscillation
            if atype == ACT_MOVE:
                consecutive_moves += 1
                if consecutive_moves > 3:
                    self.last_turn_log.append("  (move limit, ending turn)")
                    apply_action(game_state, Action(ActionType.END_TURN))
                    actions_taken += 1
                    break
            else:
                consecutive_moves = 0

            # Apply capture or move via real engine (validates + refreshes)
            from_hex = game_state.grid.get(*action[1])
            to_hex = game_state.grid.get(*action[2])
            if not game_state.move_unit(from_hex, to_hex):
                # Real engine rejected the move — fall back to END_TURN
                self.last_turn_log.append("  (rejected by engine, ending turn)")
                apply_action(game_state, Action(ActionType.END_TURN))
                actions_taken += 1
                break

        return actions_taken


# ---------------------------------------------------------------------------
# Benchmark
# ---------------------------------------------------------------------------

def benchmark(seed=42, map_width=16, map_height=12, max_depth=12, time_cap=30):
    """Run search at increasing depths and print performance table."""
    from engine import GameState

    gs = GameState(num_players=2)
    gs.setup_random_map(width=map_width, height=map_height, seed=seed)
    gs.start_turn()

    # Buy peasants for both players to create a realistic position
    for p in gs.players:
        if gs.current_player.id == p.id:
            _buy_phase(gs, p.id)
            apply_action(gs, Action(ActionType.END_TURN))
    # Now it's back to the first player's turn after cycling
    # Buy for current player too
    _buy_phase(gs, gs.current_player.id)

    pid = gs.current_player.id
    pidx = gs.current_player_idx
    nplayers = len(gs.players)

    land = sum(1 for h in gs.grid.hexes.values() if h.is_land)
    p0 = sum(1 for h in gs.grid.hexes.values() if h.owner == 0)
    p1 = sum(1 for h in gs.grid.hexes.values() if h.owner == 1)
    units = sum(1 for h in gs.grid.hexes.values() if h.has_combat_unit)

    print(f"\nAlpha-Beta Benchmark (seed={seed}, map {map_width}x{map_height})")
    print(f"Land: {land}, P0: {p0} hexes, P1: {p1} hexes, Combat units: {units}")
    print("=" * 70)
    print(f"{'Depth':<7}{'Nodes':<11}{'Time(s)':<11}{'Nodes/s':<13}{'EBF':<9}Score")
    print("-" * 70)

    prev_nodes = 0
    for depth in range(1, max_depth + 1):
        action, d, stats = search_at_depth(
            gs.grid, pidx, nplayers, pid, depth, time_cap,
        )

        nodes = stats["nodes"]
        elapsed = max(stats["elapsed"], 1e-6)
        nps = nodes / elapsed

        if prev_nodes > 0:
            ebf_str = f"{nodes / prev_nodes:.1f}"
        else:
            ebf_str = "--"

        print(f"{depth:<7}{nodes:<11}{elapsed:<11.3f}{nps:<13.0f}{ebf_str:<9}"
              f"{stats['score']:+d}")
        sys.stdout.flush()

        prev_nodes = nodes

        if elapsed > time_cap:
            print(f"\n(stopped: depth {depth} exceeded {time_cap}s cap)")
            break

    print("=" * 70)


if __name__ == "__main__":
    benchmark()
