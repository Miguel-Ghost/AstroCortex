"""Group exposures into epochs (visits). SPHEREx returns to each zone about every 6 months."""
from __future__ import annotations

import numpy as np


def group_epochs(mjds, gap_days: float = 10.0, max_span_days: float = 30.0) -> list[list[int]]:
    """Indices grouped by date: a new epoch starts after a gap > `gap_days`.

    Near the ecliptic poles SPHEREx observes almost continuously, so a group is also
    cut when it would span more than `max_span_days`.
    """
    mjds = np.asarray(mjds, dtype=float)
    if mjds.size == 0:
        return []
    order = np.argsort(mjds)
    groups: list[list[int]] = [[int(order[0])]]
    for idx in order[1:]:
        current = groups[-1]
        if (mjds[idx] - mjds[current[-1]] > gap_days) or (mjds[idx] - mjds[current[0]] > max_span_days):
            groups.append([int(idx)])
        else:
            current.append(int(idx))
    return groups
