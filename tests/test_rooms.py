"""The rooms-and-corridors generator kept for interiors."""
import random
import unittest
from collections import deque

import numpy as np

from game.rooms import generate


def reachable(walkable, start):
    """Every floor tile a walk from `start` can reach, moving in 8 directions."""
    seen, todo = {start}, deque([start])
    while todo:
        x, y = todo.popleft()
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                n = (x + dx, y + dy)
                if (0 <= n[0] < walkable.shape[0] and 0 <= n[1] < walkable.shape[1]
                        and walkable[n] and n not in seen):
                    seen.add(n)
                    todo.append(n)
    return seen


class MapTests(unittest.TestCase):
    def test_same_seed_same_map(self):
        a, _, _ = generate(80, 42, random.Random(7))
        b, _, _ = generate(80, 42, random.Random(7))
        self.assertTrue(np.array_equal(a.walkable, b.walkable))

    def test_every_floor_tile_is_reachable(self):
        for seed in range(20):
            m, start, rooms = generate(80, 42, random.Random(seed))
            self.assertGreater(len(rooms), 1)
            self.assertTrue(m.walkable[start])
            self.assertEqual(len(reachable(m.walkable, start)), int(m.walkable.sum()), seed)

    def test_the_edges_are_wall(self):
        m, _, _ = generate(80, 42, random.Random(3))
        self.assertFalse(m.walkable[0, :].any() or m.walkable[-1, :].any()
                         or m.walkable[:, 0].any() or m.walkable[:, -1].any())


if __name__ == "__main__":
    unittest.main()
