"""Explainable ranking of normalized, store-specific meal quotes. No network calls."""
from datetime import datetime, timedelta, timezone
from math import isfinite

TZ = timezone(timedelta(hours=8))
BASE_WEIGHTS = {'taste': 70, 'history': 20, 'budget': 10}
_currency = '¥'


def set_currency(symbol):
    """Let the CLI pick a symbol the active console can actually print."""
    global _currency
    _currency = symbol


def money(cents):
    return f'{_currency}{cents / 100:.2f}'


def active_weights(has_taste, has_history):
    """Drop dimensions with no evidence, then renormalize the rest to 100.

    A cold start has no taste tags and no feedback, so the only honest signal
    left is budget. Keeping a fixed 0/100 for the other two would report a score
    that looks like a preference match while actually being a price sort.
    """
    weights = {'budget': BASE_WEIGHTS['budget']}
    if has_taste:
        weights['taste'] = BASE_WEIGHTS['taste']
    if has_history:
        weights['history'] = BASE_WEIGHTS['history']
    total = sum(weights.values())
    return {name: round(value * 100 / total, 4) for name, value in weights.items()}


def weighted_score(fit, affinity, budget_ratio, has_taste, has_history):
    weights = active_weights(has_taste, has_history)
    parts = {'budget': budget_ratio, 'taste': fit, 'history': affinity}
    return sum(weights[name] * parts[name] for name in weights)


def parse_time(value):
    result = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if result.tzinfo is None:
        raise ValueError('时间必须包含时区')
    return result


def learn(profile, tags, meal, liked):
    """Store explicit feedback only; recommendations do not become history."""
    if not tags or not all(isinstance(tag, str) and tag.strip() for tag in tags):
        raise ValueError('反馈至少需要一个有效标签')
    history = profile.setdefault('feedback', {}).setdefault(meal, {})
    for tag in sorted(set(tags)):
        votes = history.setdefault(tag, {'like': 0, 'dislike': 0})
        key = 'like' if liked else 'dislike'
        votes[key] += 1
    return profile


def rank(profile, catalog, meal, budget_cents, now=None):
    now = now or datetime.now(TZ)
    if isinstance(budget_cents, bool) or not isinstance(budget_cents, int) or budget_cents <= 0:
        raise ValueError('预算必须是正整数分')
    if catalog.get('mode') not in {'demo', 'live'}:
        raise ValueError('候选数据必须明确标记 demo 或 live')
    if not isinstance(catalog.get('store_id'), str) or not catalog['store_id']:
        raise ValueError('候选数据缺少门店编号')
    forbidden = set(profile.get('avoid_tags', []))
    preferred = set(profile.get('preferred_tags', []))
    history = profile.get('feedback', {}).get(meal, {})
    category_limits = profile.get('category_limits', {})
    accepted, rejected, seen, over_budget_candidates = [], [], set(), []
    for candidate in catalog.get('candidates', []):
        name = candidate.get('name', '未命名套餐')
        try:
            cid = candidate['id']
            if not isinstance(cid, str) or cid in seen:
                raise ValueError('候选编号缺失或重复')
            seen.add(cid)
            if not candidate.get('items') or not candidate.get('available'):
                raise ValueError('缺少组成或当前不可售')
            counts = {}
            for item in candidate['items']:
                if not isinstance(item, dict) or not item.get('name') or not item.get('category'):
                    raise ValueError('餐品组成缺少名称或类别')
                quantity = item.get('quantity', 1)
                if isinstance(quantity, bool) or not isinstance(quantity, int) or quantity <= 0:
                    raise ValueError('餐品数量必须是正整数')
                category = item['category']
                counts[category] = counts.get(category, 0) + quantity
            if category_limits and not candidate.get('categories_confirmed'):
                raise ValueError('餐品类别尚未核实')
            for category, bounds in category_limits.items():
                count = counts.get(category, 0)
                if count < bounds.get('min', 0) or count > bounds.get('max', float('inf')):
                    raise ValueError(f'不符合组成习惯：{category} 数量 {count}')
            if meal not in candidate.get('meal_times', []):
                raise ValueError('不在当前餐段售卖')
            if not candidate.get('tags_confirmed'):
                raise ValueError('餐品标签未经核实')
            tags = set(candidate['tags'])
            if forbidden & tags:
                raise ValueError('包含明确忌口：' + '、'.join(sorted(forbidden & tags)))
            # Strict exclusions require verified coverage, not just absent tags.
            if not forbidden <= set(candidate.get('checked_avoid_tags', [])):
                raise ValueError('忌口信息尚未核实')
            quote = candidate['quote']
            price = quote['total_cents']
            if isinstance(price, bool) or not isinstance(price, int) or price < 0:
                raise ValueError('报价必须是非负整数分')
            if quote.get('store_id') != catalog['store_id']:
                raise ValueError('报价门店不一致')
            if quote.get('meal_time') != meal:
                raise ValueError('报价餐段不一致')
            if quote.get('source') != ('demo' if catalog['mode'] == 'demo' else 'calculate-price'):
                raise ValueError('缺少有效计价来源')
            quoted_at = parse_time(quote['quoted_at'])
            if not timedelta(0) <= now - quoted_at <= timedelta(minutes=15):
                raise ValueError('报价超过15分钟或时间异常，请重新试算')
            if quote.get('valid_until') and now > parse_time(quote['valid_until']):
                raise ValueError('优惠或报价已失效')
            if price > budget_cents:
                over = price - budget_cents
                matches = sorted(preferred & tags)
                over_budget_candidates.append({
                    'id': cid,
                    'name': name,
                    'items': candidate.get('items', []),
                    'quote': quote,
                    'tags': tags,
                    'over_cents': over,
                    'diff_yuan': f"{over / 100:.2f}",
                    'total_yuan': f"{price / 100:.2f}",
                    'target_budget': (price + 99) // 100,
                    'matched_tags': matches,
                })
                raise ValueError(f'超预算 {money(price - budget_cents)}'
                                 f'（合计 {money(price)}）')
            matches = sorted(preferred & tags)
            # Bounded, smoothed feedback; count per candidate is normalized.
            affinities = []
            for tag in tags:
                votes = history.get(tag, {})
                positive, negative = votes.get('like', 0), votes.get('dislike', 0)
                if not all(isinstance(x, int) and x >= 0 for x in (positive, negative)):
                    raise ValueError('偏好反馈计数无效')
                affinities.append((positive - negative) / (positive + negative + 2))
            affinity = sum(affinities) / max(1, len(affinities))
            fit = len(matches) / max(1, len(preferred))
            score = weighted_score(fit, affinity, 1 - price / budget_cents,
                                   bool(preferred), bool(history))
            if not isfinite(score):
                raise ValueError('推荐分数无效')
            accepted.append({**candidate, 'score': round(score, 4),
                             'matched_tags': matches, 'habit_affinity': round(affinity, 4),
                             'remaining_cents': budget_cents - price})
        except (KeyError, TypeError, ValueError) as exc:
            rejected.append({'name': name, 'reason': str(exc)})
    accepted.sort(key=lambda c: (-c['score'], c['quote']['total_cents'], c['id']))
    by_price = sorted(accepted, key=lambda c: (c['quote']['total_cents'], -c['score'], c['id']))
    # "最合口味" is only honest when a surviving candidate actually hits a tag.
    taste_hit = bool(preferred) and any(c['matched_tags'] for c in accepted)
    habit_hit = bool(history) and any(c['habit_affinity'] for c in accepted)
    if taste_hit:
        first = '最合口味'
    elif habit_hit:
        first = '习惯优先'
    elif preferred or history:
        first = '预算内可选'
    else:
        first = '价格优先'
    if taste_hit or habit_hit:
        ladder = [(first, accepted),
                  ('预算优先', by_price),
                  (('换个口味' if habit_hit else '备选方案'),
                   sorted(accepted, key=lambda c: (c['habit_affinity'], -c['score'], c['id'])))]
    else:
        # Without taste or feedback the ranking *is* a price sort. Labelling it
        # "最合口味" would claim evidence the user never provided.
        ladder = [(first, by_price), ('备选方案', by_price)]
    picks, chosen = [], {}
    for label, ordered in ladder:
        candidate = (next((c for c in ordered if c['id'] not in chosen), None)
                     if label in {'换个口味', '备选方案'} else next(iter(ordered), None))
        if candidate:
            if candidate['id'] in chosen:
                chosen[candidate['id']]['label'] += ' / ' + label
            else:
                pick = {'label': label, **candidate}
                chosen[candidate['id']] = pick
                picks.append(pick)
    upsell = None
    if not accepted and over_budget_candidates:
        if preferred:
            over_budget_candidates.sort(key=lambda c: (-len(c['matched_tags']), c['over_cents'], c['quote']['total_cents']))
        else:
            over_budget_candidates.sort(key=lambda c: (c['over_cents'], c['quote']['total_cents']))
        best = over_budget_candidates[0]
        upsell = {
            'type': 'floor',
            'badge': f"💡 仅差 ¥{best['diff_yuan']} 即可吃饱",
            'name': best['name'],
            'items': best['items'],
            'diff_yuan': best['diff_yuan'],
            'total_yuan': best['total_yuan'],
            'target_budget': best['target_budget'],
            'matched_tags': best['matched_tags'],
            'reason': f"当前预算偏紧，再加 ¥{best['diff_yuan']} 即可满足习惯组合",
        }
    elif accepted and over_budget_candidates:
        max_accepted_match = max((len(c['matched_tags']) for c in accepted), default=0)
        close = [c for c in over_budget_candidates if c['over_cents'] <= 1000 or c['over_cents'] <= budget_cents * 0.35]
        if close:
            close.sort(key=lambda c: (
                -(1 if len(c['matched_tags']) > max_accepted_match else 0),
                -len(c['matched_tags']) if preferred else 0,
                c['over_cents'],
                c['quote']['total_cents']
            ))
            best = close[0]
            if len(best['matched_tags']) > max_accepted_match:
                reason = f"仅需多加 ¥{best['diff_yuan']}，即可升级为纯 {'、'.join(best['matched_tags'])} 顶饱大满贯！"
            elif best['over_cents'] <= 300:
                reason = f"仅需多加 ¥{best['diff_yuan']}（零钱），就能从吉士堡升级为更高品质大汉堡！"
            else:
                reason = f"多花 ¥{best['diff_yuan']}，享受更加丰盛扎实的升级组合。"
            upsell = {
                'type': 'upgrade',
                'badge': f"💡 麦门进阶 · 加 ¥{best['diff_yuan']} 可升级",
                'name': best['name'],
                'items': best['items'],
                'diff_yuan': best['diff_yuan'],
                'total_yuan': best['total_yuan'],
                'target_budget': best['target_budget'],
                'matched_tags': best['matched_tags'],
                'reason': reason,
            }

    return {'mode': catalog['mode'], 'meal': meal, 'budget_cents': budget_cents,
            'store_id': catalog['store_id'], 'eligible_count': len(accepted),
            'weights': active_weights(bool(preferred), bool(history)),
            'recommendations': picks, 'rejected': rejected,
            'upsell': upsell}


WEIGHT_LABELS = {'taste': '口味匹配', 'history': '历史反馈', 'budget': '预算余量'}


def weight_note(result):
    """Say out loud which signals actually shaped this ranking."""
    weights = result.get('weights') or {}
    if set(weights) <= {'budget'}:
        return '当前没有口味偏好与反馈记录，评分只按预算余量计算，等价于价格优先。'
    trim = lambda value: f'{value:.1f}'.rstrip('0').rstrip('.')
    # Report in descending weight order, not in dict insertion order.
    order = [name for name in BASE_WEIGHTS if name in weights]
    parts = '、'.join(f"{WEIGHT_LABELS[name]} {trim(weights[name])}" for name in order)
    return f'按可用证据归一化的生效权重：{parts}（合计 100）。'


def markdown(result):
    mode = '演示数据 · 非真实菜单或报价' if result['mode'] == 'demo' else 'MCP 计价数据 · 下单前需重新确认'
    lines = ['# 麦懂你 · 用餐习惯推荐', '', mode, '',
             f"门店：{result['store_id']} ｜ 餐段：{result['meal']} ｜ 预算：{money(result['budget_cents'])}", '',
             f"在当前已收集的 {result['eligible_count']} 个合格候选中比较，不代表全菜单最低价。"]
    budget = result.get('request_budget') or {}
    if budget:
        note = f"枚举 {budget['enumerated']} 个符合组成习惯的组合，试算其中 {budget['quoted']} 个"
        if budget.get('skipped'):
            note += f"，因请求上限跳过 {budget['skipped']} 个"
        if budget.get('failed'):
            note += f"，{budget['failed']} 个未能完成计价"
        lines.append(note + '。')
        if budget.get('requests'):
            lines.append(f"本次实际请求 MCP 服务 {budget['requests']} 次。")
    elif result.get('quotes_requested'):
        note = f"枚举 {result['quotes_requested']} 个符合组成习惯的组合"
        if result.get('quotes_failed'):
            note += f"，其中 {result['quotes_failed']} 个未能完成计价"
        lines.append(note + '。')
    lines.extend([weight_note(result), ''])
    prices_only = set(result.get('weights') or {}) <= {'budget'}
    for pick in result['recommendations']:
        lines.extend([f"## {pick['label']}：{pick['name']}", '',
                      '＋'.join(f"{item['name']} × {item.get('quantity', 1)}" for item in pick['items']), '',
                      f"合计 {money(pick['quote']['total_cents'])}，预算余量 {money(pick['remaining_cents'])}。"])
        detail = []
        if not prices_only:
            detail.append('偏好匹配：' + ('、'.join(pick['matched_tags']) or '无明确偏好命中'))
            detail.append(f"历史反馈倾向：{pick['habit_affinity']:+.2f}")
        # A cold start has no taste evidence, so the score is budget headroom only.
        detail.append(f"{'预算余量得分' if prices_only else '综合分'}：{pick['score']:.2f}")
        lines.extend(['；'.join(detail) + '。', ''])
    if result.get('upsell'):
        up = result['upsell']
        lines.extend([f"## {up['badge']}：{up['name']}", '',
                      '＋'.join(f"{item['name']} × {item.get('quantity', 1)}" for item in up['items']), '',
                      f"合计 ¥{up['total_yuan']}（超出预算 ¥{up['diff_yuan']}）。{up['reason']}", ''])
    if not result['recommendations']:
        lines += ['暂无满足条件的套餐。可以更换门店、餐段或调整预算；忌口需先核实。', '']
    if result['rejected']:
        lines += ['## 排除原因', '']
        lines += [f"- {row['name']}：{row['reason']}" for row in result['rejected']]
    return '\n'.join(lines) + '\n'
