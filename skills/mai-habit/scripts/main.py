import argparse
from copy import deepcopy
from datetime import datetime
from decimal import Decimal, InvalidOperation
import json
import os
from pathlib import Path
import sys

from recommender import TZ, learn, markdown, money, rank, set_currency
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


def ask(prompt, default=''):
    """Read one answer; a blank answer keeps the default shown in the prompt."""
    try:
        answer = input(prompt).strip()
    except EOFError:
        raise ValueError('输入已中断，未写入档案') from None
    return answer or default


def ask_count(prompt, default):
    raw = ask(prompt, str(default))
    try:
        return positive(raw)
    except argparse.ArgumentTypeError as exc:
        raise ValueError(f'{exc}（收到：{raw}）') from None


SECTION_LABELS = {'burger': '主食（汉堡/卷）', 'side': '小食', 'combo': '套餐'}


def init_run(args):
    """Collect the user's own habits before anything else runs.

    Nothing is inferred here: every value comes from a flag or from an explicit
    answer, and the answers are written to the profile so later runs never have
    to guess. A blank answer accepts the printed default -- but it is still the
    user who accepted it, which is the difference from silently assuming one.
    """
    target = Path(args.out)
    if target.exists() and not args.force:
        raise ValueError(f'{target} 已存在；覆盖请加 --force，或换一个 --out 路径')
    interactive = sys.stdin.isatty()
    label = SECTION_LABELS.get(args.category, args.category)
    if args.burger is None:
        if not interactive:
            raise ValueError('非交互环境请用 --burger N --drink none|one 指定习惯')
        args.burger = ask_count(f'一餐要几份{label}？[2] ', 2)
    if args.drink is None:
        if not interactive:
            raise ValueError('非交互环境请用 --drink none|one 说明是否要饮料')
        pick = ask('要不要搭配饮料？[y/N] ', 'n').lower()
        args.drink = 'one' if pick in {'y', 'yes', '是', '要'} else 'none'
    if args.budget is None:
        if not interactive:
            raise ValueError('非交互环境请用 --budget 说明预算')
        args.budget = ask('这一餐预算多少元？[30] ', '30')
    budget_cents = cents(args.budget)
    if args.tags is None and interactive:
        args.tags = ask('固定的口味偏好，留空表示没有（例如 chicken,non_spicy）：')
    if args.avoid is None and interactive:
        args.avoid = ask('明确忌口，留空表示没有（例如 peanut）：')
    tags = [t.strip() for t in (args.tags or '').split(',') if t.strip()]
    avoid = [t.strip() for t in (args.avoid or '').split(',') if t.strip()]
    profile = {
        'source': 'user',
        'created_at': datetime.now(TZ).isoformat(timespec='seconds'),
        'category_limits': {args.category: {'min': args.burger, 'max': args.burger},
                            'drink': {'min': 1, 'max': 1} if args.drink == 'one' else {'max': 0}},
        'preferred_tags': tags,
        'avoid_tags': avoid,
        'feedback': {},
        'default_budget_cents': budget_cents,
    }
    write(target, profile)
    lines = [f'已写入 {target}（仅本机，文件权限 600，可直接编辑或删除）', '',
             f'· 每餐 {label} × {args.burger}',
             f'· {"搭配 1 份饮料" if args.drink == "one" else "不含饮料"}',
             f'· 默认预算 {money(budget_cents)}',
             f'· 口味偏好 {len(tags)} 项，忌口 {len(avoid)} 项']
    if avoid:
        lines.append(f'· 推荐时需要 --checked-avoid {",".join(avoid)} 声明已核实范围')
    lines += ['', '下一餐直接运行（预算与习惯都从档案读取）：',
              f'  python habit.py plan --profile {target} \\',
              '    --menu private/menu-response.json --mapping private/mapping.json \\',
              '    --meal lunch --store <门店编号>']
    print('\n'.join(lines))
    return 0


def warn_if_example(profile, path):
    """Say out loud when the habits being ranked are not the user's own."""
    if profile.get('source') == 'user':
        return
    print(f'注意：{path} 是示例档案（主食两份、不含饮料），不是你的习惯。'
          '先运行 python habit.py init 建档，否则这份推荐是按别人的条件算的。',
          file=sys.stderr)


def budget_of(args, profile):
    """Explicit flag wins; otherwise use the budget the user recorded at init."""
    if getattr(args, 'budget', None) is not None:
        return cents(args.budget)
    stored = profile.get('default_budget_cents')
    if isinstance(stored, int) and not isinstance(stored, bool) and stored > 0:
        return stored
    raise ValueError('请用 --budget 指定本餐预算，或先运行 habit.py init 记录默认预算')


def plan_run(args):
    """Enumerate habit-valid combinations, price them, then rank.

    Without --prices this calls calculate-price for real; with --prices it
    replays recorded responses so the whole chain is testable without a token.
    """
    profile = read(args.profile)
    warn_if_example(profile, args.profile)
    mapping = read(args.mapping)
    budget_cents = budget_of(args, profile)
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
    parser = argparse.ArgumentParser(prog='habit.py', description='麦懂你：用餐习惯套餐推荐')
    commands = parser.add_subparsers(dest='command', required=True)
    demo = commands.add_parser('demo', help='无 Token 的虚构数据演示')
    demo.add_argument('--budget', default='30')
    demo.add_argument('--meal', choices=['breakfast', 'lunch', 'dinner'], default='lunch')
    demo.add_argument('--profile', help='可选本地偏好档案 JSON')
    demo.add_argument('--json', action='store_true')
    recommend = commands.add_parser('recommend', help='对已规范化候选进行排序')
    recommend.add_argument('--profile', required=True)
    recommend.add_argument('--catalog', required=True)
    recommend.add_argument('--budget', help='本餐预算；省略则用档案里记录的默认预算')
    recommend.add_argument('--meal', choices=['breakfast', 'lunch', 'dinner'], required=True)
    recommend.add_argument('--json', action='store_true')
    feedback = commands.add_parser('feedback', help='将用户明确反馈写入本地档案')
    feedback.add_argument('--profile', required=True)
    feedback.add_argument('--meal', choices=['breakfast', 'lunch', 'dinner'], required=True)
    feedback.add_argument('--tags', required=True, help='逗号分隔的餐品口味标签')
    feedback.add_argument('--rating', choices=['like', 'dislike'], required=True)
    init = commands.add_parser('init', help='先记录你自己的用餐习惯，再开始推荐')
    init.add_argument('--out', default='private/profile.json', help='档案路径（默认 private/profile.json）')
    init.add_argument('--category', default='burger', help='主食类别键，默认 burger')
    init.add_argument('--burger', type=positive, help='一餐要几份主食')
    init.add_argument('--drink', choices=['none', 'one'], help='是否搭配一份饮料')
    init.add_argument('--budget', help='默认每餐预算（元）')
    init.add_argument('--tags', help='固定口味偏好，逗号分隔')
    init.add_argument('--avoid', help='明确忌口，逗号分隔')
    init.add_argument('--force', action='store_true', help='覆盖已有档案')
    plan = commands.add_parser('plan', help='从查询响应枚举候选、计价并排序')
    plan.add_argument('--profile', required=True)
    plan.add_argument('--mapping', required=True, help='字段映射文件，非官方接口定义')
    plan.add_argument('--menu', required=True, help='query-meals 的原始响应 JSON')
    plan.add_argument('--meal', choices=['breakfast', 'lunch', 'dinner'], required=True)
    plan.add_argument('--budget', help='本餐预算；省略则用档案里记录的默认预算')
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
                warn_if_example(profile, args.profile)
            result = rank(profile, catalog, args.meal, budget_of(args, profile), now)
            print(json.dumps(result, ensure_ascii=False, indent=2) if args.json else markdown(result))
        elif args.command == 'init':
            return init_run(args)
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
