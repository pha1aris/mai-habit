import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'skills/mai-habit/scripts'))
import adapter
import planner

TWO_BURGERS = {'burger': {'min': 2, 'max': 2}, 'drink': {'max': 0}}


def read_replay():
    mapping = json.loads((ROOT / 'examples/replay/mapping.json').read_text(encoding='utf-8'))
    menu = json.loads((ROOT / 'examples/replay/menu.json').read_text(encoding='utf-8'))
    return mapping, menu


class AdapterTests(unittest.TestCase):
    def test_dig_flattens_nested_lists(self):
        self.assertEqual([1, 2, 3], adapter.dig({'a': [{'b': [1, 2]}, {'b': [3]}]}, 'a.*.b.*'))

    def test_dig_keeps_list_shape_for_single_hit(self):
        self.assertEqual([1], adapter.dig({'a': [{'b': [1]}]}, 'a.*.b.*'))
        self.assertEqual([False], adapter.dig({'a': [{'b': False}]}, 'a.*.b'))

    def test_dig_missing_path_returns_default(self):
        self.assertIsNone(adapter.dig({'a': 1}, 'x.y'))
        self.assertEqual([], adapter.dig({'a': 1}, 'x.*'))

    def test_money_cents_respects_declared_unit(self):
        self.assertEqual(1250, adapter.money_cents('12.50'))
        self.assertEqual(1250, adapter.money_cents(1250, 'cents'))
        self.assertEqual(1200, adapter.money_cents('12'))
        self.assertEqual(1300, adapter.money_cents('¥13.00'))
        for value, unit in (('12.345', 'yuan'), (12.5, 'cents'), ('-1', 'yuan'), ('abc', 'yuan')):
            with self.subTest(value=value, unit=unit):
                with self.assertRaises(ValueError):
                    adapter.money_cents(value, unit)

    def test_category_alias_maps_store_labels(self):
        self.assertEqual('burger', adapter.category_of('汉堡'))
        self.assertEqual('drink', adapter.category_of('饮料'))
        self.assertEqual('side', adapter.category_of({'name': '小食'}))
        self.assertEqual('burger', adapter.category_of('BURGER'))
        self.assertEqual('combo', adapter.category_of('套餐'))

    def test_render_keeps_json_type_for_whole_placeholder(self):
        template = {'items': '${items}', 'store': '${store_id}', 'note': 'x-${meal}'}
        context = {'items': [{'a': 1}], 'store_id': 'S1', 'meal': 'lunch'}
        self.assertEqual({'items': [{'a': 1}], 'store': 'S1', 'note': 'x-lunch'},
                         adapter.render(template, context))
        with self.assertRaises(ValueError):
            adapter.render({'x': '${missing}'}, {})

    def test_payload_unwraps_mcp_content_envelope(self):
        self.assertEqual({'a': 1}, adapter.payload({'content': [{'type': 'text', 'text': '{"a": 1}'}]}))
        self.assertEqual({'a': 1}, adapter.payload({'a': 1}))
        # Non-JSON text must not be silently turned into a structure.
        self.assertEqual({'content': [{'type': 'text', 'text': 'PONG'}]},
                         adapter.payload({'content': [{'type': 'text', 'text': 'PONG'}]}))

    def test_meals_normalized_from_store_payload(self):
        mapping, menu = read_replay()
        items = adapter.meals(menu, mapping['menu'], 'lunch')
        self.assertEqual(7, len(items))
        by_code = {item['code']: item for item in items}
        self.assertEqual('burger', by_code['BR001']['category'])
        self.assertEqual('drink', by_code['DR001']['category'])
        self.assertEqual(1300, by_code['BR001']['price_cents'])
        self.assertEqual(['chicken', 'non_spicy'], by_code['BR003']['tags'])
        self.assertEqual('mapping', by_code['BR003']['tags_source'])

    def test_meals_without_tag_mapping_reports_no_tag_source(self):
        mapping, menu = read_replay()
        del mapping['menu']['fields']['tags']
        items = adapter.meals(menu, mapping['menu'], 'lunch')
        self.assertEqual([], items[0]['tags'])
        self.assertEqual('none', items[0]['tags_source'])

    def test_meals_rejects_missing_required_field(self):
        mapping, menu = read_replay()
        del mapping['menu']['fields']['category']
        with self.assertRaises(ValueError):
            adapter.meals(menu, mapping['menu'], 'lunch')

    def test_meals_rejects_unresolvable_list(self):
        mapping, menu = read_replay()
        mapping['menu']['list'] = 'nope.*.items'
        with self.assertRaises(ValueError):
            adapter.meals(menu, mapping['menu'], 'lunch')

    def test_quote_rejects_response_without_total(self):
        with self.assertRaises(ValueError):
            adapter.quote({'content': [{'type': 'text', 'text': '{}'}]},
                          {'total_cents': 'payPrice'}, 'S1', 'lunch')


class PlannerTests(unittest.TestCase):
    def setUp(self):
        mapping, menu = read_replay()
        self.items = adapter.meals(menu, mapping['menu'], 'lunch')

    def test_only_habit_valid_combinations_are_enumerated(self):
        combos = planner.build(self.items, TWO_BURGERS, 'lunch')
        self.assertEqual(10, len(combos))
        for combo in combos:
            self.assertEqual(2, sum(item['quantity'] for item in combo['items']))
            self.assertTrue(all(item['category'] == 'burger' for item in combo['items']))

    def test_same_dish_twice_is_a_combination(self):
        combos = planner.build(self.items, TWO_BURGERS, 'lunch')
        pairs = [combo['items'] for combo in combos]
        self.assertIn([{'code': 'BR005', 'name': '吉士汉堡', 'category': 'burger', 'quantity': 2}],
                      pairs)

    def test_combination_tags_are_the_union_of_dishes(self):
        combos = planner.build(self.items, TWO_BURGERS, 'lunch')
        by_codes = {tuple(sorted((i['code'], i['quantity']) for i in combo['items'])): combo
                    for combo in combos}
        # Two plain chicken burgers keep both tags.
        self.assertEqual(['chicken', 'non_spicy'], by_codes[(('BR003', 2),)]['tags'])
        # A mixed pair keeps the chicken tag, so a chicken preference still hits.
        self.assertEqual(['beef', 'chicken', 'spicy'],
                         by_codes[(('BR004', 1), ('BR005', 1))]['tags'])

    def test_estimate_headroom_keeps_discounted_combinations(self):
        # Menu total of a pair is 31.00; only the coupon quote decides the budget.
        self.assertEqual(10, len(planner.build(self.items, TWO_BURGERS, 'lunch', budget_cents=2500)))
        self.assertEqual([], planner.build(self.items, TWO_BURGERS, 'lunch', budget_cents=1200))

    def test_required_category_without_stock_yields_nothing(self):
        items = [item for item in self.items if item['category'] != 'burger']
        self.assertEqual([], planner.build(items, TWO_BURGERS, 'lunch'))

    def test_unbounded_maximum_uses_the_minimum_only(self):
        combos = planner.build(self.items, {'burger': {'min': 1}}, 'lunch')
        self.assertEqual(4, len(combos))
        for combo in combos:
            self.assertEqual(1, sum(item['quantity'] for item in combo['items']))

    def test_meal_filter_excludes_other_periods(self):
        items = [dict(item, meal_times=['breakfast']) for item in self.items]
        self.assertEqual([], planner.build(items, TWO_BURGERS, 'lunch'))

    def test_candidate_cap_applies_after_price_sort(self):
        combos = planner.build(self.items, TWO_BURGERS, 'lunch', max_candidates=3)
        self.assertEqual(3, len(combos))
        # Estimates use menu prices; coupons only enter through calculate-price.
        self.assertEqual([1900, 2250, 2500], [combo['estimate_cents'] for combo in combos])


class PlanCommandTests(unittest.TestCase):
    def run_cli(self, *args):
        return subprocess.run([sys.executable, str(ROOT / 'habit.py'), *args],
                              capture_output=True, text=True, encoding='utf-8', cwd=ROOT)

    def base(self, profile='examples/profile.demo.json'):
        return ['plan', '--profile', profile,
                '--mapping', 'examples/replay/mapping.json',
                '--menu', 'examples/replay/menu.json',
                '--prices', 'examples/replay/prices.json',
                '--meal', 'lunch', '--budget', '30', '--store', 'MCD-DEMO-001']

    def test_plan_replays_the_full_chain(self):
        done = self.run_cli(*self.base())
        self.assertEqual(0, done.returncode, done.stderr)
        self.assertIn('最合口味', done.stdout)
        self.assertIn('枚举 10 个符合组成习惯的组合', done.stdout)
        self.assertIn('非真实菜单或报价', done.stdout)

    def test_plan_saves_catalog_that_the_recommender_accepts(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / 'catalog.json'
            done = self.run_cli(*self.base(), '--out', str(out))
            self.assertEqual(0, done.returncode, done.stderr)
            saved = json.loads(out.read_text(encoding='utf-8'))
            self.assertEqual('demo', saved['mode'])
            self.assertEqual(10, len(saved['candidates']))
            self.assertTrue(all(c['quote']['source'] == 'demo' for c in saved['candidates']))

    def test_plan_refuses_unverified_avoid_tags(self):
        with tempfile.TemporaryDirectory() as tmp:
            profile = json.loads((ROOT / 'examples/profile.json').read_text(encoding='utf-8'))
            profile['avoid_tags'] = ['peanut']
            path = Path(tmp) / 'profile.json'
            path.write_text(json.dumps(profile, ensure_ascii=False), encoding='utf-8')
            done = self.run_cli(*self.base(str(path)))
            self.assertEqual(1, done.returncode)
            self.assertIn('忌口', done.stderr)
            self.assertEqual('', done.stdout)


if __name__ == '__main__':
    unittest.main()
