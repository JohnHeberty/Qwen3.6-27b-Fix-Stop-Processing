"""Tarefas difíceis (multi-arquivo) para o A/B agêntico. Cada uma tem "files" (estado inicial,
com bugs / feature faltando) e "solution" (arquivos que, sobrepostos, fazem os testes passarem;
usado só pelo --selftest para provar que a tarefa é solúvel)."""
TEST_CMD = "python3 -m unittest discover -s tests -v"  # igual ao de tasks.py

HARD = {}

# =======================================================================================
_LEXER_OK = '''import re

TOKEN_RE = re.compile(r"\\s*(?:(\\d+\\.\\d*|\\.\\d+|\\d+)|([A-Za-z_]\\w*)|(\\*\\*|[-+*/^(),=]))")


class Token:
    def __init__(self, kind, value):
        self.kind, self.value = kind, value

    def __repr__(self):
        return f"Token({self.kind!r}, {self.value!r})"


def tokenize(src):
    """Numbers (int or float), names, operators. '**' is an alias of '^'."""
    pos, out = 0, []
    src = src.rstrip()
    while pos < len(src):
        m = TOKEN_RE.match(src, pos)
        if not m:
            raise SyntaxError(f"bad character at {pos}: {src[pos]!r}")
        num, name, op = m.groups()
        if num is not None:
            out.append(Token("num", float(num) if "." in num else int(num)))
        elif name is not None:
            out.append(Token("name", name))
        else:
            out.append(Token("op", "^" if op == "**" else op))
        pos = m.end()
    out.append(Token("eof", None))
    return out
'''
_LEXER_BUG = _LEXER_OK.replace(r'(\\d+\\.\\d*|\\.\\d+|\\d+)', r'(\\d+|\\.\\d+)')

_PARSER_OK = '''from .lexer import tokenize

# Grammar (lowest to highest precedence):
#   stmt   := NAME '=' expr | expr
#   expr   := term (('+'|'-') term)*
#   term   := unary (('*'|'/') unary)*
#   unary  := '-' unary | power          (so -2^2 == -(2^2) == -4)
#   power  := atom ('^' unary)?          (right-associative: 2^3^2 == 2^(3^2))
#   atom   := NUM | NAME | NAME '(' args ')' | '(' expr ')'


class Parser:
    def __init__(self, src):
        self.toks = tokenize(src)
        self.i = 0

    def peek(self):
        return self.toks[self.i]

    def take(self, kind=None, value=None):
        t = self.toks[self.i]
        if (kind and t.kind != kind) or (value is not None and t.value != value):
            raise SyntaxError(f"expected {value or kind}, got {t}")
        self.i += 1
        return t

    def parse(self):
        node = self.stmt()
        self.take("eof")
        return node

    def stmt(self):
        t, nxt = self.toks[self.i], self.toks[self.i + 1]
        if t.kind == "name" and nxt.kind == "op" and nxt.value == "=":
            self.i += 2
            return ("assign", t.value, self.expr())
        return self.expr()

    def expr(self):
        node = self.term()
        while self.peek().kind == "op" and self.peek().value in "+-":
            op = self.take().value
            node = (op, node, self.term())
        return node

    def term(self):
        node = self.unary()
        while self.peek().kind == "op" and self.peek().value in "*/":
            op = self.take().value
            node = (op, node, self.unary())
        return node

    def unary(self):
        if self.peek().kind == "op" and self.peek().value == "-":
            self.take()
            return ("neg", self.unary())
        return self.power()

    def power(self):
        base = self.atom()
        if self.peek().kind == "op" and self.peek().value == "^":
            self.take()
            return ("^", base, self.unary())
        return base

    def atom(self):
        t = self.take()
        if t.kind == "num":
            return ("num", t.value)
        if t.kind == "name":
            if self.peek().kind == "op" and self.peek().value == "(":
                self.take()
                args = []
                if not (self.peek().kind == "op" and self.peek().value == ")"):
                    args.append(self.expr())
                    while self.peek().kind == "op" and self.peek().value == ",":
                        self.take()
                        args.append(self.expr())
                self.take("op", ")")
                return ("call", t.value, args)
            return ("var", t.value)
        if t.kind == "op" and t.value == "(":
            node = self.expr()
            self.take("op", ")")
            return node
        raise SyntaxError(f"unexpected {t}")


def parse(src):
    return Parser(src).parse()
'''
# bug 2: unary binds tighter than ^ ; bug 3: ^ left-assoc via loop
_PARSER_BUG = _PARSER_OK.replace('''    def unary(self):
        if self.peek().kind == "op" and self.peek().value == "-":
            self.take()
            return ("neg", self.unary())
        return self.power()

    def power(self):
        base = self.atom()
        if self.peek().kind == "op" and self.peek().value == "^":
            self.take()
            return ("^", base, self.unary())
        return base
''', '''    def unary(self):
        return self.power()

    def power(self):
        if self.peek().kind == "op" and self.peek().value == "-":
            self.take()
            base = ("neg", self.atom())
        else:
            base = self.atom()
        while self.peek().kind == "op" and self.peek().value == "^":
            self.take()
            base = ("^", base, self.atom())
        return base
''')

_EVAL_OK = '''from .parser import parse

FUNCS = {"max": max, "min": min, "abs": abs, "sum": lambda *a: sum(a)}


class Interpreter:
    def __init__(self):
        self.env = {"pi": 3.141592653589793}

    def run(self, src):
        """Evaluate one statement; assignments return the assigned value."""
        return self.ev(parse(src))

    def ev(self, n):
        kind = n[0]
        if kind == "num":
            return n[1]
        if kind == "var":
            if n[1] not in self.env:
                raise NameError(f"undefined variable {n[1]!r}")
            return self.env[n[1]]
        if kind == "assign":
            self.env[n[1]] = self.ev(n[2])
            return self.env[n[1]]
        if kind == "neg":
            return -self.ev(n[1])
        if kind == "call":
            if n[1] not in FUNCS:
                raise NameError(f"undefined function {n[1]!r}")
            return FUNCS[n[1]](*[self.ev(a) for a in n[2]])
        a, b = self.ev(n[1]), self.ev(n[2])
        if kind == "+":
            return a + b
        if kind == "-":
            return a - b
        if kind == "*":
            return a * b
        if kind == "/":
            if b == 0:
                raise ZeroDivisionError("division by zero")
            return a / b
        if kind == "^":
            return a ** b
        raise ValueError(f"bad node {n!r}")
'''
# bug 4: only first argument passed
_EVAL_BUG = _EVAL_OK.replace("return FUNCS[n[1]](*[self.ev(a) for a in n[2]])",
                             "return FUNCS[n[1]](self.ev(n[2][0])) if n[2] else FUNCS[n[1]]()")

_FMT_OK = '''def fmt(value):
    """Integers (and floats with integral value) print without a decimal point; other floats
    are rounded to 6 decimals with trailing zeros stripped. Never prints '-0'."""
    if isinstance(value, float):
        if value == int(value):
            value = int(value)
        else:
            s = f"{value:.6f}".rstrip("0").rstrip(".")
            return "0" if s in ("-0", "0") else s
    if value == 0:
        return "0"
    return str(value)
'''
# bug 5: -0.0 -> "-0" ; and 2.0 -> "2.0"
_FMT_BUG = '''def fmt(value):
    """Integers (and floats with integral value) print without a decimal point; other floats
    are rounded to 6 decimals with trailing zeros stripped. Never prints '-0'."""
    if isinstance(value, float):
        s = f"{value:.6f}".rstrip("0")
        return s
    return str(value)
'''

_CALC_TESTS = '''import unittest

from calc.evaluator import Interpreter
from calc.formatter import fmt
from calc.lexer import tokenize


def run(src, it=None):
    return fmt((it or Interpreter()).run(src))


class TestLexer(unittest.TestCase):
    def test_float_literals(self):
        vals = [t.value for t in tokenize("3.25 + .5 + 7.")][:-1]
        self.assertEqual(vals, [3.25, "+", 0.5, "+", 7.0])

    def test_double_star_alias(self):
        self.assertEqual([t.value for t in tokenize("2**3")][:-1], [2, "^", 3])


class TestPrecedence(unittest.TestCase):
    def test_basic(self):
        self.assertEqual(run("1 + 2 * 3"), "7")
        self.assertEqual(run("(1 + 2) * 3"), "9")

    def test_power_right_assoc(self):
        self.assertEqual(run("2 ^ 3 ^ 2"), "512")

    def test_unary_minus_vs_power(self):
        self.assertEqual(run("-2 ^ 2"), "-4")
        self.assertEqual(run("(-2) ^ 2"), "4")
        self.assertEqual(run("2 ^ -1"), "0.5")

    def test_double_negation(self):
        self.assertEqual(run("--3"), "3")


class TestEvaluator(unittest.TestCase):
    def test_functions_multi_arg(self):
        self.assertEqual(run("max(1, 7, 3)"), "7")
        self.assertEqual(run("min(4, 2)"), "2")
        self.assertEqual(run("sum(1, 2, 3, 4)"), "10")

    def test_assignment_and_vars(self):
        it = Interpreter()
        self.assertEqual(run("x = 2.5", it), "2.5")
        self.assertEqual(run("y = x * 4", it), "10")
        self.assertEqual(run("y ^ 2 - x", it), "97.5")

    def test_errors(self):
        with self.assertRaises(NameError):
            Interpreter().run("nope + 1")
        with self.assertRaises(ZeroDivisionError):
            Interpreter().run("1 / 0")


class TestFormatter(unittest.TestCase):
    def test_integral_float(self):
        self.assertEqual(fmt(2.0), "2")

    def test_rounding(self):
        self.assertEqual(fmt(1 / 3), "0.333333")
        self.assertEqual(fmt(0.1 + 0.2), "0.3")

    def test_negative_zero(self):
        self.assertEqual(fmt(-0.0), "0")
        self.assertEqual(run("-0 * 1.5"), "0")


if __name__ == "__main__":
    unittest.main()
'''

HARD["minilang-bugs"] = {
    "prompt": "The `calc` package is a small expression interpreter (lexer -> parser -> evaluator -> "
              "formatter). Its test suite tests/test_calc.py has many failures. There are several "
              "independent bugs spread across different modules. Find and fix ALL of them in the source "
              f"code (do not change the tests). Run the tests with `{TEST_CMD}` until everything passes.",
    "files": {
        "calc/__init__.py": "",
        "calc/lexer.py": _LEXER_BUG,
        "calc/parser.py": _PARSER_BUG,
        "calc/evaluator.py": _EVAL_BUG,
        "calc/formatter.py": _FMT_BUG,
        "tests/__init__.py": "",
        "tests/test_calc.py": _CALC_TESTS,
    },
    "solution": {"calc/lexer.py": _LEXER_OK, "calc/parser.py": _PARSER_OK,
                 "calc/evaluator.py": _EVAL_OK, "calc/formatter.py": _FMT_OK},
}

# =======================================================================================
_MONEY = '''from decimal import Decimal, ROUND_HALF_UP


class Money:
    """Immutable amount in integer cents of one currency."""
    __slots__ = ("cents", "currency")

    def __init__(self, cents, currency):
        if not isinstance(cents, int):
            raise TypeError("cents must be int")
        object.__setattr__(self, "cents", cents)
        object.__setattr__(self, "currency", currency.upper())

    def __setattr__(self, *_):
        raise AttributeError("Money is immutable")

    @classmethod
    def parse(cls, text):
        """'12.34 usd' -> Money(1234, 'USD')"""
        amount, cur = text.split()
        cents = int((Decimal(amount) * 100).quantize(Decimal(1), rounding=ROUND_HALF_UP))
        return cls(cents, cur)

    def __add__(self, other):
        if other.currency != self.currency:
            raise ValueError("currency mismatch")
        return Money(self.cents + other.cents, self.currency)

    def __eq__(self, other):
        return isinstance(other, Money) and (self.cents, self.currency) == (other.cents, other.currency)

    def __hash__(self):
        return hash((self.cents, self.currency))

    def __repr__(self):
        return f"Money({self.cents}, {self.currency!r})"

    def __str__(self):
        sign = "-" if self.cents < 0 else ""
        c = abs(self.cents)
        return f"{sign}{c // 100}.{c % 100:02d} {self.currency}"
'''
_RATES_START = '''from decimal import Decimal, ROUND_HALF_UP

from .money import Money


class RateTable:
    """Exchange rates. add("USD", "EUR", "0.9") means 1 USD = 0.9 EUR."""

    def __init__(self):
        self._rates = {}

    def add(self, src, dst, rate):
        self._rates[(src.upper(), dst.upper())] = Decimal(str(rate))

    def rate(self, src, dst):
        """Direct rate; TODO: identity (same currency), the inverse of a known pair, and a cross rate
        through ONE intermediate currency (e.g. EUR->BRL via USD) when no direct/inverse pair exists.
        KeyError when none of these works."""
        return self._rates[(src.upper(), dst.upper())]

    def convert(self, money, dst):
        """TODO: convert Money to dst, rounding half-up to whole cents."""
        raise NotImplementedError
'''
_RATES_OK = '''from decimal import Decimal, ROUND_HALF_UP

from .money import Money


class RateTable:
    """Exchange rates. add("USD", "EUR", "0.9") means 1 USD = 0.9 EUR."""

    def __init__(self):
        self._rates = {}

    def add(self, src, dst, rate):
        self._rates[(src.upper(), dst.upper())] = Decimal(str(rate))

    def rate(self, src, dst):
        src, dst = src.upper(), dst.upper()
        if src == dst:
            return Decimal(1)
        if (src, dst) in self._rates:
            return self._rates[(src, dst)]
        if (dst, src) in self._rates:
            return Decimal(1) / self._rates[(dst, src)]
        for mid in {c for pair in self._rates for c in pair} - {src, dst}:
            try:
                return self._direct_or_inverse(src, mid) * self._direct_or_inverse(mid, dst)
            except KeyError:
                continue
        raise KeyError(f"no rate {src}->{dst}")

    def _direct_or_inverse(self, src, dst):
        if (src, dst) in self._rates:
            return self._rates[(src, dst)]
        if (dst, src) in self._rates:
            return Decimal(1) / self._rates[(dst, src)]
        raise KeyError(f"no rate {src}->{dst}")

    def convert(self, money, dst):
        r = self.rate(money.currency, dst)
        cents = int((Decimal(money.cents) * r).quantize(Decimal(1), rounding=ROUND_HALF_UP))
        return Money(cents, dst)
'''
_LEDGER_START = '''import datetime

from .money import Money


class Entry:
    def __init__(self, date, money, memo=""):
        self.date = datetime.date.fromisoformat(date) if isinstance(date, str) else date
        self.money, self.memo = money, memo


class Ledger:
    def __init__(self, rates):
        self.rates = rates
        self.entries = []

    def add(self, date, amount, memo=""):
        """amount like '12.34 USD' (negative for expenses)."""
        self.entries.append(Entry(date, Money.parse(amount), memo))

    def balance(self, currency):
        """TODO: sum of all entries converted (entry by entry) to `currency`."""
        raise NotImplementedError

    def monthly_report(self, currency):
        """TODO: [('YYYY-MM', Money), ...] sorted by month, each entry converted to `currency`
        before summing; months with no entries are omitted."""
        raise NotImplementedError
'''
_LEDGER_OK = _LEDGER_START.replace('''    def balance(self, currency):
        """TODO: sum of all entries converted (entry by entry) to `currency`."""
        raise NotImplementedError

    def monthly_report(self, currency):
        """TODO: [('YYYY-MM', Money), ...] sorted by month, each entry converted to `currency`
        before summing; months with no entries are omitted."""
        raise NotImplementedError
''', '''    def balance(self, currency):
        total = Money(0, currency)
        for e in self.entries:
            total = total + self.rates.convert(e.money, currency)
        return total

    def monthly_report(self, currency):
        months = {}
        for e in self.entries:
            k = e.date.strftime("%Y-%m")
            months[k] = months.get(k, Money(0, currency)) + self.rates.convert(e.money, currency)
        return sorted(months.items())
''')
_LEDGER_TESTS = '''import unittest

from ledger.ledger import Ledger
from ledger.money import Money
from ledger.rates import RateTable


def table():
    t = RateTable()
    t.add("USD", "EUR", "0.9")
    t.add("USD", "BRL", "5.0")
    return t


class TestRates(unittest.TestCase):
    def test_identity_and_inverse(self):
        t = table()
        self.assertEqual(t.rate("eur", "EUR"), 1)
        self.assertEqual(t.rate("BRL", "USD"), t.rate("USD", "BRL") ** -1)

    def test_cross_rate(self):
        t = table()
        self.assertEqual(t.convert(Money(-2000, "EUR"), "BRL"), Money(-11111, "BRL"))  # via USD

    def test_missing_pair(self):
        with self.assertRaises(KeyError):
            table().rate("EUR", "JPY")

    def test_convert_rounding_half_up(self):
        t = table()
        self.assertEqual(t.convert(Money(1001, "USD"), "EUR"), Money(901, "EUR"))   # 900.9 -> 901
        self.assertEqual(t.convert(Money(5, "USD"), "EUR"), Money(5, "EUR"))        # 4.5 -> 5
        self.assertEqual(t.convert(Money(1000, "BRL"), "USD"), Money(200, "USD"))
        self.assertEqual(t.convert(Money(-1001, "USD"), "EUR"), Money(-901, "EUR"))


class TestLedger(unittest.TestCase):
    def make(self):
        lg = Ledger(table())
        lg.add("2026-01-05", "100.00 USD", "salary")
        lg.add("2026-01-20", "-20.00 EUR", "dinner")
        lg.add("2026-03-02", "50.00 BRL", "refund")
        lg.add("2026-01-31", "0.05 USD", "interest")
        return lg

    def test_balance_usd(self):
        # 100.00 + (-20 EUR -> -22.22 USD) + (50 BRL -> 10.00 USD) + 0.05
        self.assertEqual(self.make().balance("USD"), Money(8783, "USD"))

    def test_balance_brl(self):
        # 500.00 + (-20 EUR -> -111.11 BRL) + 50.00 + 0.25
        self.assertEqual(self.make().balance("BRL"), Money(43914, "BRL"))

    def test_monthly_report(self):
        rep = self.make().monthly_report("USD")
        self.assertEqual([m for m, _ in rep], ["2026-01", "2026-03"])
        self.assertEqual(rep[0][1], Money(7783, "USD"))
        self.assertEqual(rep[1][1], Money(1000, "USD"))

    def test_empty(self):
        lg = Ledger(table())
        self.assertEqual(lg.balance("EUR"), Money(0, "EUR"))
        self.assertEqual(lg.monthly_report("EUR"), [])

    def test_str(self):
        self.assertEqual(str(self.make().balance("USD")), "87.83 USD")


if __name__ == "__main__":
    unittest.main()
'''
HARD["ledger-feature"] = {
    "prompt": "Finish the multi-currency support in the `ledger` package: RateTable.rate must handle the "
              "identity, the inverse of a known pair and cross rates through one intermediate currency, RateTable.convert must convert with half-up "
              "rounding to cents, and Ledger.balance / Ledger.monthly_report must be implemented (see "
              "their docstrings). The spec is tests/test_ledger.py (do not change it). "
              f"Run the tests with `{TEST_CMD}` until everything passes.",
    "files": {
        "ledger/__init__.py": "",
        "ledger/money.py": _MONEY,
        "ledger/rates.py": _RATES_START,
        "ledger/ledger.py": _LEDGER_START,
        "tests/__init__.py": "",
        "tests/test_ledger.py": _LEDGER_TESTS,
    },
    "solution": {"ledger/rates.py": _RATES_OK, "ledger/ledger.py": _LEDGER_OK},
}
