"""Map raw MCD MCP responses onto this project's internal contract.

Field paths always come from the caller's mapping file. This module never
guesses a field name, so an unverified response can never look like a real one.
"""
from datetime import datetime
from decimal import Decimal, InvalidOperation
import json
import re

PLACEHOLDER = re.compile(r'\$\{(\w+)\}')

CATEGORY_ALIASES = {
    'burger': 'burger', 'burgers': 'burger', 'sandwich': 'burger',
    '汉堡': 'burger', '汉堡包': 'burger', '主食': 'burger',
    'drink': 'drink', 'drinks': 'drink', 'beverage': 'drink',
    '饮料': 'drink', '饮品': 'drink',
    'side': 'side', 'sides': 'side', 'snack': 'side',
    '小食': 'side', '配餐': 'side', '小食配餐': 'side',
    'dessert': 'dessert', '甜品': 'dessert', '冰品': 'dessert',
    'combo': 'combo', 'meal': 'combo', '套餐': 'combo',
}


def dig(data, path, default=None):
    """Resolve a dot path; '*' flattens a list or dict of children."""
    if not path:
        return default
    parts = [p for p in str(path).split('.') if p]
    flatten = '*' in parts
    nodes = [data]
    for part in parts:
        found = []
        for node in nodes:
            if node is None:
                continue
            if part == '*':
                if isinstance(node, list):
                    found.extend(node)
                elif isinstance(node, dict):
                    found.extend(node.values())
            elif isinstance(node, dict):
                if part in node:
                    found.append(node[part])
            elif isinstance(node, list) and part.isdigit():
                index = int(part)
                if 0 <= index < len(node):
                    found.append(node[index])
        nodes = [n for n in found if n is not None]
        if not nodes:
            return [] if flatten else default
    if flatten:
        return nodes
    return nodes[0] if nodes else default


def payload(raw):
    """Unwrap the standard MCP content envelope when its text carries JSON."""
    if isinstance(raw, dict) and isinstance(raw.get('content'), list):
        for part in raw['content']:
            if part.get('type') == 'text' and isinstance(part.get('text'), str):
                try:
                    return json.loads(part['text'])
                except ValueError:
                    return raw
    return raw


def render(template, context):
    """Fill ${name} placeholders; a whole placeholder keeps its JSON type."""
    if isinstance(template, dict):
        return {key: render(value, context) for key, value in template.items()}
    if isinstance(template, list):
        return [render(value, context) for value in template]
    if not isinstance(template, str):
        return template
    whole = PLACEHOLDER.fullmatch(template.strip())
    if whole:
        return _value(whole.group(1), context)

    def replace(match):
        return str(_value(match.group(1), context))

    return PLACEHOLDER.sub(replace, template)


def _value(name, context):
    if name not in context:
        raise ValueError(f'计价参数模板引用了未知变量：{name}')
    return context[name]


def money_cents(value, unit='yuan'):
    """Convert a yuan or cents amount to non-negative integer cents.

    The unit is declared by the mapping file so 12 is never silently read as
    1200 cents or the other way round.
    """
    if value is None:
        return None
    try:
        number = Decimal(str(value).replace('¥', '').replace('￥', '').strip())
    except (InvalidOperation, ValueError):
        raise ValueError(f'无法识别的金额：{value!r}') from None
    if not number.is_finite() or number < 0:
        raise ValueError(f'金额非法：{value!r}')
    if unit == 'cents':
        if number != number.to_integral_value():
            raise ValueError(f'以分为单位时必须是整数：{value!r}')
        return int(number)
    if unit != 'yuan':
        raise ValueError(f'未支持的金额单位：{unit!r}')
    scaled = number * 100
    if scaled != scaled.to_integral_value():
        raise ValueError(f'金额最多两位小数：{value!r}')
    return int(scaled)


def category_of(value, overrides=None):
    """Translate a store category label into burger/drink/side/... tokens."""
    if isinstance(value, dict):
        value = value.get('name') or value.get('code') or ''
    text = str(value or '').strip()
    table = {**CATEGORY_ALIASES, **(overrides or {})}
    if text.lower() in table:
        return table[text.lower()]
    return table.get(text, text.lower() or 'other')


def meals(raw, mapping, meal):
    """Normalize query-meals into a flat list of sellable menu items."""
    rows = dig(payload(raw), mapping.get('list'), [])
    if not isinstance(rows, list) or not rows:
        raise ValueError('菜单列表路径没有定位到非空数组，请先核对映射文件')
    fields = mapping.get('fields') or {}
    for key in ('code', 'name', 'category'):
        if not fields.get(key):
            raise ValueError(f'映射文件缺少必需字段：{key}')
    has_tags = bool(fields.get('tags'))
    has_price = bool(fields.get('price'))
    price_unit = mapping.get('price_unit', 'yuan')
    items = []
    for row in rows:
        code = dig(row, fields['code'])
        name = dig(row, fields['name'])
        if code is None or name is None:
            continue
        raw_tags = dig(row, fields['tags'], []) if has_tags else []
        if isinstance(raw_tags, str):
            raw_tags = [raw_tags]
        if not isinstance(raw_tags, list):
            raw_tags = []
        raw_meal_times = dig(row, fields.get('meal_times'), None)
        if not isinstance(raw_meal_times, list) or not raw_meal_times:
            raw_meal_times = [meal]
        price = money_cents(dig(row, fields['price']), price_unit) if has_price else None
        items.append({
            'code': str(code),
            'name': str(name),
            'category': category_of(dig(row, fields['category']), mapping.get('categories')),
            'price_cents': price,
            'available': bool(dig(row, fields['available'], True)
                              if fields.get('available') else True),
            'meal_times': [str(x) for x in raw_meal_times],
            'tags': sorted({str(t).strip() for t in raw_tags if str(t).strip()}),
            'tags_confirmed': True,
            'tags_source': 'mapping' if has_tags else 'none',
        })
    if not items:
        raise ValueError('映射后没有任何可用餐品，请检查字段路径')
    return items


def quote(raw, mapping, store_id, meal, source='calculate-price', now=None):
    """Normalize calculate-price into one quote object for a single candidate."""
    body = payload(raw)
    total = money_cents(dig(body, mapping.get('total_cents') or mapping.get('total')),
                        mapping.get('price_unit', 'yuan'))
    if total is None:
        raise ValueError('计价响应没有定位到应付总价')
    valid_until = dig(body, mapping.get('valid_until')) if mapping.get('valid_until') else None
    return {
        'source': source,
        'store_id': store_id,
        'meal_time': meal,
        'total_cents': total,
        'quoted_at': (now or datetime.now().astimezone()).isoformat(),
        'valid_until': valid_until,
    }


def catalog(mode, store_id, candidates):
    """Wrap candidates in the contract that the recommender validates."""
    if mode not in {'demo', 'live'}:
        raise ValueError('mode 必须是 demo 或 live')
    return {'mode': mode, 'store_id': store_id, 'candidates': candidates}
