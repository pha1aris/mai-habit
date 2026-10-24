"""Guard: the browser demo and the Python pipeline must enumerate the same combos.

`docs/index.html` re-implements planner.build in JavaScript so the page can run
with no backend. Two implementations of one rule drift unless something checks
them against each other, so this compares the full enumeration for three habit
shapes.

Amounts are intentionally not compared: the demo prices from menu list prices,
the CLI from calculate-price (which includes coupons). Presenting a summed list
price as the payable total is the exact thing this project refuses to do, so
comparing them as if they should be equal would be the wrong assertion.

Usage:
    python tools/verify_demo_parity.py [--node /path/to/node]
"""
import argparse
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'skills/mai-habit/scripts'))
import adapter
import planner

SHAPES = [
    ('B2_D0', {'burger': {'min': 2, 'max': 2}, 'drink': {'max': 0}}),
    ('B1_D0', {'burger': {'min': 1, 'max': 1}, 'drink': {'max': 0}}),
    ('B2_D1', {'burger': {'min': 2, 'max': 2}, 'drink': {'min': 1, 'max': 1}}),
]


def combo_key(combo):
    return '+'.join(f"{i['code']}x{i.get('quantity', 1)}" for i in combo['items'])


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--node', default='node', help='node 可执行文件，默认走 PATH')
    args = parser.parse_args()

    try:
        done = subprocess.run([args.node, str(ROOT / 'tools/check_demo_parity.js')],
                              capture_output=True, text=True, encoding='utf-8', cwd=ROOT)
    except FileNotFoundError:
        print(f'找不到 node：{args.node}。用 --node 指定路径，或先安装 Node.js。', file=sys.stderr)
        return 2
    if done.returncode != 0:
        print('演示页算法提取失败：\n' + (done.stderr or done.stdout), file=sys.stderr)
        return 2

    demo = json.loads(done.stdout)
    mapping = json.loads((ROOT / 'examples/replay/mapping.json').read_text(encoding='utf-8'))
    menu = json.loads((ROOT / 'examples/replay/menu.json').read_text(encoding='utf-8'))
    items = adapter.meals(menu, mapping['menu'], 'lunch')

    failed = 0
    for name, limits in SHAPES:
        expected = [combo_key(c) for c in planner.build(items, limits, 'lunch')]
        actual = demo['enumeration'][name]
        if expected == actual:
            print(f'{name}: {len(expected)} 个组合，一致')
            continue
        failed += 1
        print(f'{name}: 不一致（python {len(expected)} / js {len(actual)}）', file=sys.stderr)
        for index, (left, right) in enumerate(zip(expected, actual)):
            if left != right:
                print(f'  第 {index + 1} 项 python={left} js={right}', file=sys.stderr)
        if len(expected) != len(actual):
            print(f'  数量不同：python={expected}\n            js={actual}', file=sys.stderr)

    if failed:
        print(f'\n{failed} 组枚举不一致：演示页与命令行的组合规则已经分叉。', file=sys.stderr)
        return 1
    print('\n枚举一致：演示页与命令行按同一套规则生成候选。')
    return 0


if __name__ == '__main__':
    sys.exit(main())
