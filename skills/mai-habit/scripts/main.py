import argparse
from copy import deepcopy
from datetime import datetime
from decimal import Decimal, InvalidOperation
import json
import os
from pathlib import Path
import sys

from recommender import TZ, learn, markdown, rank, set_currency
from mcp_client import Client, MCPError
import adapter
import console
import planner

ROOT = Path(__file__).resolve().parents[3]


def read(path):
    """Read one JSON document, naming the file and the line when it is broken."""
    try:
        text = Path(path).read_text(encoding='utf-8')
    except UnicodeDecodeError:
        raise ValueError(f'{path} 不是 UTF-8 编码，请另存为 UTF-8 后重试') from None
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f'{path} 不是有效 JSON：第 {exc.lineno} 行第 {exc.colno} 列 {exc.msg}') from None


def write(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    # Atomic replacement; private file mode where the OS supports it.
    temp = path.with_suffix(path.suffix + '.tmp')
    fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, 'w', encoding='utf-8') as out:
        json.dump(value, out, ensure_ascii=False, indent=2)
        out.write('\n')
    temp.replace(path)


def cents(value):
    try:
        number = Decimal(value)
        if not number.is_finite() or number <= 0 or number * 100 != (number * 100).to_integral_value():
            raise ValueError('预算需大于0，最多两位小数')
        return int(number * 100)
    except InvalidOperation:
        raise ValueError('预算需为有效金额') from None


def plan_run(args):
    """Enumerate habit-valid combinations, price them, then rank.

    Without --prices this calls calculate-price for real; with --prices it
    replays recorded responses so the whole chain is testable without a token.
    """
    profile = read(args.profile)
    mapping = read(args.mapping)
    budget_cents = cents(args.budget)
    checked = [t.strip() for t in (args.checked_avoid or '').split(',') if t.strip()]
    if profile.get('avoid_tags') and not set(profile['avoid_tags']) <= set(checked):
        raise ValueError('档案含忌口但未声明核实范围，请用 --checked-avoid 指明已核实的忌口')
    items = adapter.meals(read(args.menu), mapping.get('menu') or {}, args.meal)
    stats = {}
    combos = planner.build(items, profile.get('category_limits') or {}, args.meal,
                           budget_cents, max_candidates=args.max_quotes, stats=stats)
    if not combos:
        missing = stats.get('missing_category')
        if missing:
            raise ValueError(f'当前菜单没有可售的 {missing} 类餐品，无法满足组成习惯')
        raise ValueError('按当前习惯与预算没有可枚举的候选组合')
    now = datetime.now(TZ)
    quotes, client = {}, None
    if args.prices:
        for entry in read(args.prices).get('quotes', []):
            key = frozenset((i['code'], i['quantity']) for i in entry.get('items', []))
            quotes[key] = entry.get('response')
        source, mode = 'demo', 'demo'
    else:
        client = Client(os.environ.get('MCD_MCP_TOKEN', ''))
        client.initialize()
        client.warm()  # one tools/list for the whole run, not one per candidate
        source, mode = 'calculate-price', 'live'
    request = dict(mapping.get('price_request') or {})
    item_template = request.pop('itemTemplate', None)
    candidates, failures = [], {}

    def note(reason):
        """Count each failure reason; one mapping bug should be readable as one."""
        failures[reason] = failures.get(reason, 0) + 1

    for index, combo in enumerate(combos, 1):
        key = frozenset((i['code'], i['quantity']) for i in combo['items'])
        if client is None:
            raw = quotes.get(key)
            if raw is None:
                note('回放样本缺少该组合的计价响应')
                continue
        else:
            if item_template is None:
                raise ValueError('映射文件缺少 price_request.itemTemplate')
            context = {'store_id': args.store, 'meal': args.meal,
                       'items': [adapter.render(item_template, dict(item))
                                 for item in combo['items']]}
            raw = client.call('calculate-price', adapter.render(request, context))
        try:
            ticket = adapter.quote(raw, mapping.get('quote') or {},
                                   args.store, args.meal, source, now)
        except ValueError as exc:
            note(str(exc))
            continue
        candidates.append({
            'id': f'combo-{index:02d}',
            'name': '＋'.join(f"{i['name']}×{i['quantity']}" for i in combo['items']),
            'items': combo['items'],
            'tags': combo['tags'],
            'tags_confirmed': True,
            'categories_confirmed': True,
            'checked_avoid_tags': checked,
            'available': True,
            'meal_times': [args.meal],
            'quote': ticket,
        })
    if not candidates:
        raise ValueError('所有候选都未能完成计价。' + top_reasons(failures))
    catalog = adapter.catalog(mode, args.store, candidates)
    result = rank(profile, catalog, args.meal, budget_cents, now)
    result['quotes_requested'] = len(combos)
    result['quotes_failed'] = sum(failures.values())
    result['request_budget'] = {
        'enumerated': stats.get('generated', len(combos)),
        'quoted': len(combos),
        'skipped': stats.get('skipped', 0),
        'estimate_dropped': stats.get('estimate_dropped', 0),
        'failed': result['quotes_failed'],
        'requests': client.calls if client else 0,
    }
    if failures:
        result['failure_reasons'] = dict(sorted(failures.items(), key=lambda kv: -kv[1]))
    return result, catalog


def top_reasons(failures, limit=3):
    """Turn per-candidate failures into one diagnosable sentence."""
    if not failures:
        return ''
    ranked = sorted(failures.items(), key=lambda kv: -kv[1])[:limit]
    return '主要原因：' + '；'.join(f'{count} 次「{reason}」' for reason, count in ranked)


def positive(value):
    """argparse type for a count that must be at least 1."""
    try:
        number = int(value)
    except (TypeError, ValueError):
        raise argparse.ArgumentTypeError('需要一个正整数') from None
    if number < 1 or number > 200:
        raise argparse.ArgumentTypeError('取值范围 1-200')
    return number


def main():
    set_currency(console.prepare())
    parser = argparse.ArgumentParser(description='麦懂你：用餐习惯套餐推荐')
    commands = parser.add_subparsers(dest='command', required=True)
    demo = commands.add_parser('demo', help='无 Token 的虚构数据演示')
    demo.add_argument('--budget', default='30')
    demo.add_argument('--meal', choices=['breakfast', 'lunch', 'dinner'], default='lunch')
    demo.add_argument('--profile', help='可选本地偏好档案 JSON')
    demo.add_argument('--json', action='store_true')
    recommend = commands.add_parser('recommend', help='对已规范化候选进行排序')
    recommend.add_argument('--profile', required=True)
    recommend.add_argument('--catalog', required=True)
    recommend.add_argument('--budget', required=True)
    recommend.add_argument('--meal', choices=['breakfast', 'lunch', 'dinner'], required=True)
    recommend.add_argument('--json', action='store_true')
    feedback = commands.add_parser('feedback', help='将用户明确反馈写入本地档案')
    feedback.add_argument('--profile', required=True)
    feedback.add_argument('--meal', choices=['breakfast', 'lunch', 'dinner'], required=True)
    feedback.add_argument('--tags', required=True, help='逗号分隔的餐品口味标签')
    feedback.add_argument('--rating', choices=['like', 'dislike'], required=True)
    plan = commands.add_parser('plan', help='从查询响应枚举候选、计价并排序')
    plan.add_argument('--profile', required=True)
    plan.add_argument('--mapping', required=True, help='字段映射文件，非官方接口定义')
    plan.add_argument('--menu', required=True, help='query-meals 的原始响应 JSON')
    plan.add_argument('--meal', choices=['breakfast', 'lunch', 'dinner'], required=True)
    plan.add_argument('--budget', required=True)
    plan.add_argument('--store', required=True)
    plan.add_argument('--prices', help='calculate-price 回放样本；省略则实时调用 MCP')
    plan.add_argument('--checked-avoid', help='已核实不含的忌口，逗号分隔')
    plan.add_argument('--max-quotes', type=positive, default=planner.MAX_CANDIDATES,
                      help=f'最多试算多少个组合（默认 {planner.MAX_CANDIDATES}），用于控制调用额度')
    plan.add_argument('--out', help='把规范化候选保存到私有目录')
    plan.add_argument('--json', action='store_true')
    commands.add_parser('mcp-tools', help='连接官方服务并显示实际工具参数结构')
    call = commands.add_parser('mcp-call', help='调用单个只读或计价工具')
    call.add_argument('--tool', required=True)
    call.add_argument('--args', required=True, help='本地 JSON 参数文件')
    call.add_argument('--out', required=True, help='私有结果文件，勿提交至 GitHub')
    args = parser.parse_args()
    try:
        if args.command in {'demo', 'recommend'}:
            now = datetime.now(TZ)
            if args.command == 'demo':
                profile = read(args.profile or ROOT / 'examples/profile.demo.json')
                catalog = deepcopy(read(ROOT / 'examples/catalog.demo.json'))
                for candidate in catalog['candidates']:
                    candidate['quote']['quoted_at'] = now.isoformat()
                    candidate['quote']['meal_time'] = args.meal
            else:
                profile, catalog = read(args.profile), read(args.catalog)
            result = rank(profile, catalog, args.meal, cents(args.budget), now)
            print(json.dumps(result, ensure_ascii=False, indent=2) if args.json else markdown(result))
        elif args.command == 'plan':
            result, catalog = plan_run(args)
            if args.out:
                write(args.out, catalog)
                print(f'已保存规范化候选到 {args.out}', file=sys.stderr)
            print(json.dumps(result, ensure_ascii=False, indent=2) if args.json else markdown(result))
        elif args.command == 'feedback':
            profile = read(args.profile)
            learn(profile, [t.strip() for t in args.tags.split(',')], args.meal, args.rating == 'like')
            write(args.profile, profile)
            print('已记录明确反馈。下次推荐会按餐段使用这些偏好。')
        else:
            client = Client(os.environ.get('MCD_MCP_TOKEN', ''))
            client.initialize()
            if args.command == 'mcp-tools':
                print(json.dumps(client.tools(), ensure_ascii=False, indent=2))
            else:
                arguments = read(args.args)
                result = client.call(args.tool, arguments)
                write(args.out, {'tool': args.tool, 'queried_at': datetime.now(TZ).isoformat(), 'result': result})
                print('已保存查询结果到本地文件。结果可能含个人信息，请勿公开提交。')
    except FileNotFoundError as exc:
        hint = f'：{exc.filename}' if exc.filename else ''
        print(f'错误：找不到文件{hint}', file=sys.stderr)
        return 1
    except (MCPError, ValueError) as exc:
        # Our own errors are safe to quote; they never contain tokens or payloads.
        print('错误：' + str(exc), file=sys.stderr)
        return 1
    except (KeyError, TypeError, OSError):
        # Server payloads and parameter files may carry personal data: never echo them.
        print('错误：文件或数据结构错误，请核对输入文件', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
