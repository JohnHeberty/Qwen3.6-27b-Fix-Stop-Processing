"""Mini-tarefas de código para o A/B agêntico (agent_ab.py).

Cada tarefa é um repositório minúsculo com testes `unittest` (stdlib; o host não tem pytest)
que FALHAM no estado inicial. O harness dá as ferramentas do OpenCode 2 (read/write/edit/
glob/grep/shell) ao modelo e, no fim, restaura os arquivos de teste originais e roda
`python3 -m unittest discover -s tests` -- como o avaliador do SWE-bench Pro, que reseta os
testes antes de pontuar. Sucesso = código de saída 0.
"""

TEST_CMD = "python3 -m unittest discover -s tests -v"

TASKS = {}

# ---------------------------------------------------------------------------------------
TASKS["slugify-bug"] = {
    "prompt": "The tests in tests/test_text_utils.py are failing. Find and fix the bug(s) in the "
              f"source code (do not change the tests). Run the tests with `{TEST_CMD}`.",
    "files": {
        "text_utils.py": '''import re
import unicodedata


def slugify(text, sep="-"):
    """Lowercase ASCII slug: accents removed, runs of non-alphanumerics -> one separator,
    no separator at the ends."""
    text = unicodedata.normalize("NFKD", text)
    text = text.lower()
    text = re.sub(r"[^a-z0-9]", sep, text)
    return text


def truncate_words(text, n):
    """First n words, followed by '...' only if something was cut."""
    words = text.split()
    if len(words) < n:
        return text
    return " ".join(words[:n]) + "..."
''',
        "tests/__init__.py": "",
        "tests/test_text_utils.py": '''import unittest

from text_utils import slugify, truncate_words


class TestSlugify(unittest.TestCase):
    def test_basic(self):
        self.assertEqual(slugify("Hello World"), "hello-world")

    def test_accents(self):
        self.assertEqual(slugify("Ação é Ótima"), "acao-e-otima")

    def test_collapse_and_strip(self):
        self.assertEqual(slugify("  --Hello,   World!!  "), "hello-world")

    def test_custom_sep(self):
        self.assertEqual(slugify("a b  c", sep="_"), "a_b_c")


class TestTruncate(unittest.TestCase):
    def test_no_cut(self):
        self.assertEqual(truncate_words("one two three", 3), "one two three")

    def test_cut(self):
        self.assertEqual(truncate_words("one two three four", 2), "one two...")


if __name__ == "__main__":
    unittest.main()
''',
    },
}

# ---------------------------------------------------------------------------------------
TASKS["intervals-impl"] = {
    "prompt": "Implement `merge_intervals` and `total_covered` in intervals.py so that the tests in "
              f"tests/test_intervals.py pass. Do not change the tests. Run them with `{TEST_CMD}`.",
    "files": {
        "intervals.py": '''def merge_intervals(intervals):
    """Merge overlapping or touching closed intervals [a, b] (a <= b).

    Input may be unsorted and is not modified. Returns a new sorted list of [a, b] lists.
    """
    raise NotImplementedError


def total_covered(intervals):
    """Total length covered by the union of the intervals."""
    raise NotImplementedError
''',
        "tests/__init__.py": "",
        "tests/test_intervals.py": '''import unittest

from intervals import merge_intervals, total_covered


class TestMerge(unittest.TestCase):
    def test_empty(self):
        self.assertEqual(merge_intervals([]), [])

    def test_overlap_unsorted(self):
        self.assertEqual(merge_intervals([[8, 10], [1, 3], [2, 6], [15, 18]]), [[1, 6], [8, 10], [15, 18]])

    def test_touching(self):
        self.assertEqual(merge_intervals([[1, 4], [4, 5]]), [[1, 5]])

    def test_nested(self):
        self.assertEqual(merge_intervals([[1, 10], [2, 3], [4, 8]]), [[1, 10]])

    def test_input_not_modified(self):
        data = [[3, 4], [1, 2]]
        merge_intervals(data)
        self.assertEqual(data, [[3, 4], [1, 2]])


class TestTotal(unittest.TestCase):
    def test_total(self):
        self.assertEqual(total_covered([[1, 3], [2, 6], [8, 10]]), 7)

    def test_total_empty(self):
        self.assertEqual(total_covered([]), 0)


if __name__ == "__main__":
    unittest.main()
''',
    },
}

# ---------------------------------------------------------------------------------------
TASKS["inventory-multi"] = {
    "prompt": "Our inventory package has bugs: the tests in tests/test_store.py fail. Investigate the "
              "package (inventory/), fix the source so all tests pass, and keep the public API. "
              f"Do not change the tests. Run them with `{TEST_CMD}`.",
    "files": {
        "inventory/__init__.py": "from .models import Item\nfrom .store import Store, OutOfStock\n",
        "inventory/models.py": '''from dataclasses import dataclass


@dataclass
class Item:
    sku: str
    name: str
    unit_price: float
    qty: int = 0

    @property
    def value(self):
        return self.unit_price * self.qty
''',
        "inventory/store.py": '''from .models import Item


class OutOfStock(Exception):
    pass


class Store:
    def __init__(self):
        self._items = {}

    def add(self, sku, name, unit_price, qty=0):
        if sku in self._items:
            self._items[sku].qty += qty
        else:
            self._items[sku] = Item(sku, name, unit_price, qty)
        return self._items[sku]

    def remove(self, sku, qty):
        item = self._items[sku]
        item.qty -= qty
        return item

    def total_value(self):
        return round(sum(i.unit_price for i in self._items.values()), 2)

    def low_stock(self, threshold=5):
        return sorted(i.sku for i in self._items.values() if i.qty < threshold)
''',
        "tests/__init__.py": "",
        "tests/test_store.py": '''import unittest

from inventory import Store, OutOfStock


class TestStore(unittest.TestCase):
    def setUp(self):
        self.s = Store()
        self.s.add("A1", "bolt", 0.25, 100)
        self.s.add("B2", "nut", 0.10, 3)
        self.s.add("C3", "gear", 12.5, 5)

    def test_add_existing_accumulates(self):
        self.s.add("A1", "bolt", 0.25, 20)
        self.assertEqual(self.s._items["A1"].qty, 120)

    def test_total_value(self):
        self.assertAlmostEqual(self.s.total_value(), 25.0 + 0.30 + 62.5)

    def test_remove(self):
        self.s.remove("A1", 40)
        self.assertEqual(self.s._items["A1"].qty, 60)

    def test_remove_too_many_raises_and_keeps_stock(self):
        with self.assertRaises(OutOfStock):
            self.s.remove("B2", 4)
        self.assertEqual(self.s._items["B2"].qty, 3)

    def test_remove_unknown_raises_keyerror(self):
        with self.assertRaises(KeyError):
            self.s.remove("ZZ", 1)

    def test_low_stock_inclusive(self):
        self.assertEqual(self.s.low_stock(5), ["B2", "C3"])


if __name__ == "__main__":
    unittest.main()
''',
    },
}

# ---------------------------------------------------------------------------------------
TASKS["lru-cache"] = {
    "prompt": "Create lru.py with a class `LRUCache(capacity)` that satisfies tests/test_lru.py. "
              f"Do not change the tests. Run them with `{TEST_CMD}`.",
    "files": {
        "README.md": "# lru\n\nA tiny LRU cache. See tests/test_lru.py for the expected behaviour.\n",
        "tests/__init__.py": "",
        "tests/test_lru.py": '''import unittest

from lru import LRUCache


class TestLRU(unittest.TestCase):
    def test_get_missing_returns_default(self):
        c = LRUCache(2)
        self.assertIsNone(c.get("x"))
        self.assertEqual(c.get("x", 7), 7)

    def test_eviction_order(self):
        c = LRUCache(2)
        c.put("a", 1)
        c.put("b", 2)
        c.get("a")          # a becomes most recent
        c.put("c", 3)       # evicts b
        self.assertIsNone(c.get("b"))
        self.assertEqual(c.get("a"), 1)
        self.assertEqual(c.get("c"), 3)

    def test_put_existing_updates_and_refreshes(self):
        c = LRUCache(2)
        c.put("a", 1)
        c.put("b", 2)
        c.put("a", 10)
        c.put("c", 3)       # evicts b, not a
        self.assertEqual(c.get("a"), 10)
        self.assertIsNone(c.get("b"))

    def test_len_and_contains(self):
        c = LRUCache(3)
        for k in "abcd":
            c.put(k, k.upper())
        self.assertEqual(len(c), 3)
        self.assertIn("d", c)
        self.assertNotIn("a", c)

    def test_capacity_must_be_positive(self):
        with self.assertRaises(ValueError):
            LRUCache(0)


if __name__ == "__main__":
    unittest.main()
''',
    },
}

# ---------------------------------------------------------------------------------------
TASKS["csv-report"] = {
    "prompt": "report.py produces a wrong summary: tests/test_report.py fails. Fix report.py so the "
              f"tests pass (do not change the tests or data/sales.csv). Run them with `{TEST_CMD}`.",
    "files": {
        "data/sales.csv": "category,item,amount\nbooks,novel,12.50\ntools,hammer,30.00\n"
                          "books,atlas,40.25\nfood,apple,1.10\ntools,saw,25.00\nfood,bread,3.40\n",
        "report.py": '''import csv
import os

HERE = os.path.dirname(os.path.abspath(__file__))


def load(path=os.path.join(HERE, "data", "sales.csv")):
    with open(path, newline="") as f:
        rows = list(csv.reader(f))
    out = []
    for cat, item, amount in rows:
        out.append({"category": cat, "item": item, "amount": float(amount)})
    return out


def summarize(rows):
    """{category: total} rounded to 2 decimals, as a list of (category, total) sorted by
    total descending, then category ascending."""
    totals = {}
    for r in rows:
        totals[r["category"]] = totals.get(r["category"], 0) + r["amount"]
    return sorted(totals.items(), key=lambda kv: kv[1])
''',
        "tests/__init__.py": "",
        "tests/test_report.py": '''import unittest

from report import load, summarize


class TestReport(unittest.TestCase):
    def test_load_skips_header(self):
        rows = load()
        self.assertEqual(len(rows), 6)
        self.assertEqual(rows[0], {"category": "books", "item": "novel", "amount": 12.5})

    def test_summary_order_and_rounding(self):
        self.assertEqual(summarize(load()), [("tools", 55.0), ("books", 52.75), ("food", 4.5)])

    def test_tie_breaks_by_name(self):
        rows = [{"category": "b", "item": "x", "amount": 1.0}, {"category": "a", "item": "y", "amount": 1.0}]
        self.assertEqual(summarize(rows), [("a", 1.0), ("b", 1.0)])


if __name__ == "__main__":
    unittest.main()
''',
    },
}

# Tarefas difíceis, multi-arquivo (tasks_hard.py): um interpretador com 5 bugs em 4 módulos e
# uma feature multi-moeda que atravessa 3 módulos (inclui taxa cruzada).
from tasks_hard import HARD  # noqa: E402

TASKS.update(HARD)
