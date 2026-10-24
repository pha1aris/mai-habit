from copy import deepcopy
from datetime import datetime, timedelta
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'skills/mai-habit/scripts'))
from recommender import TZ, learn, rank


class RecommendationTests(unittest.TestCase):
    def setUp(self):
        self.profile = json.loads((ROOT / 'examples/profile.json').read_text(encoding='utf-8'))
        self.catalog = json.loads((ROOT / 'examples/catalog.demo.json').read_text(encoding='utf-8'))
        self.now = datetime(2026, 10, 24, 12, tzinfo=TZ)

    def run_rank(self, budget=3000, catalog=None, profile=None):
        return rank(profile or self.profile, catalog or self.catalog, 'lunch', budget, self.now)

    def test_two_burgers_no_drink_and_affordable(self):
        result = self.run_rank()
        self.assertEqual(3, result['eligible_count'])
        for row in result['recommendations']:
            self.assertEqual(2, sum(i.get('quantity', 1) for i in row['items'] if i['category'] == 'burger'))
            self.assertFalse(any(i['category'] == 'drink' for i in row['items']))
            self.assertLessEqual(row['quote']['total_cents'], 3000)

    def test_low_budget_does_not_relax_habits(self):
        result = self.run_rank(1500)
        self.assertEqual([], result['recommendations'])
        self.assertEqual(6, len(result['rejected']))

    def test_cold_start_prefers_lowest_price(self):
        self.assertEqual('value-pair', self.run_rank()['recommendations'][0]['id'])

    def test_feedback_changes_choice_in_selected_meal_only(self):
        # Equal price and explicit preference: only feedback should change ordering.
        catalog = deepcopy(self.catalog)
        catalog['candidates'] = [catalog['candidates'][0], catalog['candidates'][2]]
        for row in catalog['candidates']:
            row['quote']['total_cents'] = 2500
        catalog['candidates'][0]['tags'] = ['chicken']
        catalog['candidates'][1]['tags'] = ['beef']
        profile = deepcopy(self.profile)
        self.assertEqual('chicken-pair', self.run_rank(catalog=catalog, profile=profile)['recommendations'][0]['id'])
        learn(profile, ['beef'], 'dinner', True)
        self.assertEqual('chicken-pair', self.run_rank(catalog=catalog, profile=profile)['recommendations'][0]['id'])
        learn(profile, ['beef'], 'lunch', True)
        self.assertEqual('mixed-pair', self.run_rank(catalog=catalog, profile=profile)['recommendations'][0]['id'])

    def test_ranking_does_not_mutate_history(self):
        before = deepcopy(self.profile)
        self.run_rank()
        self.assertEqual(before, self.profile)

    def test_drink_exclusion_even_with_two_burgers(self):
        self.catalog['candidates'] = [self.catalog['candidates'][4]]
        self.assertFalse(self.run_rank()['recommendations'])

    def test_stale_wrong_store_wrong_meal_and_unconfirmed_categories(self):
        for mutation in ('stale', 'store', 'meal', 'categories'):
            with self.subTest(mutation=mutation):
                catalog = deepcopy(self.catalog)
                catalog['candidates'] = [catalog['candidates'][0]]
                row = catalog['candidates'][0]
                if mutation == 'stale':
                    row['quote']['quoted_at'] = (self.now - timedelta(minutes=16)).isoformat()
                elif mutation == 'store':
                    row['quote']['store_id'] = 'OTHER'
                elif mutation == 'meal':
                    row['quote']['meal_time'] = 'dinner'
                else:
                    row['categories_confirmed'] = False
                self.assertFalse(self.run_rank(catalog=catalog)['recommendations'])

    def test_live_rejects_demo_quotes(self):
        self.catalog['mode'] = 'live'
        self.assertFalse(self.run_rank()['recommendations'])

    def test_unknown_or_present_avoid_tag_excluded(self):
        self.profile['avoid_tags'] = ['peanut']
        self.assertFalse(self.run_rank()['recommendations'])
        for row in self.catalog['candidates']:
            row['checked_avoid_tags'] = ['peanut']
        self.assertTrue(self.run_rank()['recommendations'])
        for row in self.catalog['candidates']:
            row['tags'].append('peanut')
        self.assertFalse(self.run_rank()['recommendations'])

    def test_expired_coupon_excluded_before_fifteen_minutes(self):
        for row in self.catalog['candidates']:
            row['quote']['valid_until'] = (self.now - timedelta(seconds=1)).isoformat()
        self.assertFalse(self.run_rank()['recommendations'])

    def test_negative_price_and_fractional_quantity_excluded(self):
        self.catalog['candidates'] = [self.catalog['candidates'][0]]
        self.catalog['candidates'][0]['quote']['total_cents'] = -100
        self.assertFalse(self.run_rank()['recommendations'])
        self.catalog['candidates'][0]['quote']['total_cents'] = 2000
        self.catalog['candidates'][0]['items'][0]['quantity'] = 0.5
        self.assertFalse(self.run_rank()['recommendations'])

    def test_cold_start_labels_do_not_claim_taste_evidence(self):
        result = self.run_rank()
        picks = result['recommendations']
        self.assertEqual('价格优先', picks[0]['label'])
        self.assertEqual({'budget'}, set(result['weights']))
        self.assertNotIn('最合口味', ''.join(p['label'] for p in picks))
        self.assertEqual(len(picks), len({p['id'] for p in picks}))

    def test_single_candidate_merges_labels_without_duplicates(self):
        profile = json.loads((ROOT / 'examples/profile.demo.json').read_text(encoding='utf-8'))
        catalog = deepcopy(self.catalog)
        catalog['candidates'] = [catalog['candidates'][0]]
        picks = self.run_rank(catalog=catalog, profile=profile)['recommendations']
        self.assertEqual(1, len(picks))
        self.assertEqual('最合口味 / 预算优先', picks[0]['label'])

    def test_weights_renormalize_around_available_evidence(self):
        profile = json.loads((ROOT / 'examples/profile.demo.json').read_text(encoding='utf-8'))
        # Taste tags plus lunch feedback reproduce the documented 70/20/10 split.
        self.assertEqual({'taste': 70.0, 'history': 20.0, 'budget': 10.0},
                         self.run_rank(profile=profile)['weights'])
        # Taste tags but no feedback for this meal: 80 points renormalized to 100.
        no_history = deepcopy(profile)
        no_history['feedback'] = {}
        self.assertEqual({'taste': 87.5, 'budget': 12.5},
                         self.run_rank(profile=no_history)['weights'])
        # Feedback but no taste tags: the remaining 30 points carry the score.
        history_only = deepcopy(profile)
        history_only['preferred_tags'] = []
        self.assertEqual({'budget': 33.3333, 'history': 66.6667},
                         self.run_rank(profile=history_only)['weights'])


    def test_commercial_upsell_mechanism(self):
        # 场景 A：预算过低时，给出离吃饱差额最近的底线推荐
        floor_result = self.run_rank(1500)
        self.assertIsNotNone(floor_result.get('upsell'))
        self.assertEqual('floor', floor_result['upsell']['type'])
        self.assertEqual('3.90', floor_result['upsell']['diff_yuan'])
        self.assertEqual(19, floor_result['upsell']['target_budget'])

        # 场景 B：预算充足时，给出加钱升级的高品质/进阶推荐
        upgrade_result = self.run_rank(2800)
        self.assertIsNotNone(upgrade_result.get('upsell'))
        self.assertEqual('upgrade', upgrade_result['upsell']['type'])
        self.assertEqual('8.90', upgrade_result['upsell']['diff_yuan'])
        self.assertEqual(37, upgrade_result['upsell']['target_budget'])


if __name__ == '__main__':
    unittest.main()
