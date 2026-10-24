"""Enumerate habit-constrained meal combinations from a normalized store menu."""
from itertools import combinations_with_replacement

POOL_LIMIT = 6
MAX_CANDIDATES = 40


def cheapest(items, category, meal, limit=POOL_LIMIT):
    """Cheapest sellable items of one category; the combination decides quantity."""
    pool = [item for item in items
            if item.get('category') == category
            and item.get('available', True)
            and meal in item.get('meal_times', [])]
    pool.sort(key=lambda item: (item.get('price_cents', 0), item['code'], item.get('name', '')))
    return pool[:limit]


def _choices(pool, low, high):
    """Multiset choices of size low..high; the same dish may repeat."""
    for size in range(low, high + 1):
        if size == 0:
            yield {}
            continue
        for picks in combinations_with_replacement(range(len(pool)), size):
            counts = {}
            for index in picks:
                code = pool[index]['code']
                counts[code] = counts.get(code, 0) + 1
            yield counts


def _all_tags(items):
    """Union of dish tags: one matching dish is enough to describe the combination.

    Union also makes avoid-tag checks strict, since any dish carrying a forbidden
    tag will surface it on the combination.
    """
    tags = set()
    for item in items:
        tags.update(item.get('tags', []))
    return sorted(tags)


def bounds_of(category_limits):
    """Read one category limit; an unbounded maximum means 'only the minimum'."""
    plan = {}
    for category, bounds in sorted(category_limits.items()):
        low = max(0, int(bounds.get('min', 0)))
        high = bounds.get('max', low)
        # JSON null or infinity both mean "no stated ceiling"; the minimum wins.
        if high is None or high == float('inf'):
            high = low
        high = max(low, int(high))
        # Cap the fan-out so one loose habit cannot explode the call budget.
        plan[category] = (low, min(high, low + 2))
    return plan


def build(items, category_limits, meal, budget_cents=None, limit=POOL_LIMIT,
          max_candidates=MAX_CANDIDATES, overflow=1.5, stats=None):
    """Return price-sorted combinations that already satisfy the stated habits.

    ``budget_cents`` only bounds how many quotes get requested: a coupon can pull
    a menu-priced combination under budget, so the estimate is never treated as
    the final total. Truncation means the result is never a claim about the
    whole menu. When ``stats`` is passed it is filled with what was cut and why,
    so the CLI can say it out loud instead of truncating silently.
    """
    ceiling = int(budget_cents * overflow) if budget_cents else None
    pools = {}
    for category, (low, high) in bounds_of(category_limits).items():
        pool = cheapest(items, category, meal, limit)
        if high and not pool:
            # A required category has nothing sellable; report no candidates.
            if stats is not None:
                stats.update({'generated': 0, 'kept': 0, 'skipped': 0,
                              'estimate_dropped': 0, 'missing_category': category})
            return []
        pools[category] = (low, high, pool)
    combinations = [{}]
    for category, (low, high, pool) in pools.items():
        merged = []
        for base in combinations:
            for counts in _choices(pool, low, high):
                merged.append({**base, **counts})
        combinations = merged
    by_code = {item['code']: item for item in items}
    results, estimate_dropped = [], 0
    for counts in combinations:
        if not counts:
            continue
        dishes = [by_code[code] for code in counts]
        estimate = sum(by_code[code].get('price_cents', 0) * count
                       for code, count in counts.items())
        if ceiling is not None and estimate > ceiling:
            estimate_dropped += 1
            continue
        results.append({
            'items': [{'code': code, 'name': by_code[code].get('name', code),
                       'category': by_code[code]['category'], 'quantity': count}
                      for code, count in sorted(counts.items())],
            'estimate_cents': estimate,
            'tags': _all_tags(dishes),
        })
    results.sort(key=lambda row: (row['estimate_cents'], [i['code'] for i in row['items']]))
    kept = results[:max_candidates]
    if stats is not None:
        stats.update({'generated': len(results), 'kept': len(kept),
                      'skipped': len(results) - len(kept),
                      'estimate_dropped': estimate_dropped})
    return kept
