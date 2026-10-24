"""The browser demo must not drift from the Python pipeline.

`docs/index.html` is what most visitors will actually open, so it has to be
honest about the same things the CLI is honest about: the menu it prices, what
kind of data it is, and which price it is quoting.
"""
import json
from pathlib import Path
import re
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'skills/mai-habit/scripts'))
import adapter

HTML = ROOT / 'docs/index.html'


def demo_menu():
    """Parse the MENU literal the way a reader would: by its declared fields."""
    text = HTML.read_text(encoding='utf-8')
    block = text[text.index('const MENU = ['):text.index('];', text.index('const MENU = ['))]
    rows = re.findall(
        r"\{\s*code:\s*'([^']+)',\s*name:\s*'([^']+)',\s*cat:\s*'([^']+)',\s*"
        r"cents:\s*(\d+),\s*tags:\s*\[([^\]]*)\]\s*\}", block)
    items = []
    for code, name, cat, cents, tags in rows:
        tag_list = re.findall(r"'([^']+)'", tags)
        items.append({'code': code, 'name': name, 'category': cat,
                      'price_cents': int(cents), 'tags': sorted(tag_list)})
    return items


class DemoSyncTests(unittest.TestCase):
    def setUp(self):
        self.demo = demo_menu()
        mapping = json.loads((ROOT / 'examples/replay/mapping.json').read_text(encoding='utf-8'))
        menu = json.loads((ROOT / 'examples/replay/menu.json').read_text(encoding='utf-8'))
        self.pipeline = adapter.meals(menu, mapping['menu'], 'lunch')

    def test_menu_is_identical_to_the_pipeline_sample(self):
        def shape(items):
            return sorted((i['code'], i['name'], i['category'], i['price_cents'],
                           tuple(sorted(i.get('tags', [])))) for i in items)
        self.assertEqual(shape(self.pipeline), shape(self.demo))

    def test_composition_labels_cover_every_category_in_the_menu(self):
        cats = {item['category'] for item in self.demo}
        self.assertEqual({'burger', 'drink', 'side'}, cats)

    def test_price_count_is_a_list_price_estimate_not_a_payable_total(self):
        # The project's own rule: never present summed list prices as the amount
        # actually payable. The demo has to say which one it is showing.
        text = HTML.read_text(encoding='utf-8')
        self.assertIn('菜单标价', text)
        self.assertIn('calculate-price', text)
        self.assertIn('保守估算', text)

    def test_fictional_data_is_labelled_above_the_fold(self):
        text = HTML.read_text(encoding='utf-8')
        head = text[:text.index('</header>')]
        self.assertIn('虚构菜单', head)
        self.assertIn('非真实报价', head)

    def test_no_placeholder_links_or_todo_left_in_the_page(self):
        text = HTML.read_text(encoding='utf-8')
        for marker in ('TODO', 'FIXME', '<your-account>', 'example.com'):
            self.assertNotIn(marker, text)


if __name__ == '__main__':
    unittest.main()
