"""Prioritized and bounded alias pairs; strong blocking keys are processed first."""

import re
from collections import defaultdict
from datetime import timedelta
from itertools import combinations

from rapidfuzz.fuzz import token_set_ratio

from darknetra.analytics.link_scoring import phash_distance


def candidate_pairs(profiles, max_pairs=5000):
    pairs = set()

    def add(a, b):
        if a.id != b.id:
            pairs.add(tuple(sorted((a.id, b.id))))
        return len(pairs) >= max_pairs

    ordered = sorted(profiles, key=lambda p: p.id)
    for attr in ("fingerprints", "contacts", "wallets"):
        index = defaultdict(list)
        for profile in ordered:
            for key in getattr(profile, attr):
                index[key].append(profile)
        for key in sorted(index):
            for a, b in combinations(index[key], 2):
                if add(a, b):
                    return pairs, True
    # Bounded comparisons prevent quadratic work even when few pairs qualify.
    comparisons, max_comparisons = 0, max(10000, max_pairs * 20)
    for a, b in combinations(ordered, 2):
        comparisons += 1
        if comparisons > max_comparisons:
            return pairs, True
        image = any(phash_distance(x, y) <= 8 for x in a.image_hashes for y in b.image_hashes)

        def normalize(value):
            return re.sub(r"[^\w\s]", " ", value.casefold())

        similar = token_set_ratio(normalize(a.value), normalize(b.value)) >= 85
        window = (
            a.timestamps
            and b.timestamps
            and min(a.timestamps) <= max(b.timestamps) + timedelta(days=30)
            and min(b.timestamps) <= max(a.timestamps) + timedelta(days=30)
        )
        if (
            image
            or similar
            or (a.platforms & b.platforms and window and len(a.terms & b.terms) >= 2)
        ):
            if add(a, b):
                return pairs, True
    return pairs, False
