"""Суммы в рублях: форматирование и запись прописью, как принято в договорах."""

from decimal import ROUND_HALF_UP, Decimal

_UNITS_M = ["", "один", "два", "три", "четыре", "пять", "шесть", "семь", "восемь", "девять"]
_UNITS_F = ["", "одна", "две", "три", "четыре", "пять", "шесть", "семь", "восемь", "девять"]
_TEENS = ["десять", "одиннадцать", "двенадцать", "тринадцать", "четырнадцать", "пятнадцать",
          "шестнадцать", "семнадцать", "восемнадцать", "девятнадцать"]
_TENS = ["", "", "двадцать", "тридцать", "сорок", "пятьдесят", "шестьдесят", "семьдесят",
         "восемьдесят", "девяносто"]
_HUNDREDS = ["", "сто", "двести", "триста", "четыреста", "пятьсот", "шестьсот", "семьсот",
             "восемьсот", "девятьсот"]

# (формы для 1, 2-4, 5+; женский род)
_SCALES = [
    (("", "", ""), False),
    (("тысяча", "тысячи", "тысяч"), True),
    (("миллион", "миллиона", "миллионов"), False),
    (("миллиард", "миллиарда", "миллиардов"), False),
]


def plural(n: int, forms: tuple[str, str, str]) -> str:
    n = abs(n) % 100
    if 11 <= n <= 19:
        return forms[2]
    n %= 10
    if n == 1:
        return forms[0]
    if 2 <= n <= 4:
        return forms[1]
    return forms[2]


def _triad(n: int, feminine: bool) -> list[str]:
    words = [_HUNDREDS[n // 100]]
    rest = n % 100
    if 10 <= rest <= 19:
        words.append(_TEENS[rest - 10])
    else:
        words.append(_TENS[rest // 10])
        words.append((_UNITS_F if feminine else _UNITS_M)[rest % 10])
    return [w for w in words if w]


def int_to_words(n: int) -> str:
    if n == 0:
        return "ноль"
    parts: list[str] = []
    for scale, (forms, feminine) in enumerate(_SCALES):
        triad = n // (1000 ** scale) % 1000
        if not triad:
            continue
        chunk = _triad(triad, feminine)
        if scale:
            chunk.append(plural(triad, forms))
        parts = chunk + parts
    return " ".join(parts)


def to_decimal(value) -> Decimal:
    return Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def format_amount(value) -> str:
    """125400.5 -> '125 400,50'"""
    d = to_decimal(value)
    rub, kop = divmod(int(d * 100), 100)
    return f"{rub:,}".replace(",", " ") + f",{kop:02d}"


def amount_in_words(value) -> str:
    """125400.5 -> '125 400 (сто двадцать пять тысяч четыреста) рублей 50 копеек'"""
    d = to_decimal(value)
    rub, kop = divmod(int(d * 100), 100)
    rub_str = f"{rub:,}".replace(",", " ")
    return (
        f"{rub_str} ({int_to_words(rub)}) {plural(rub, ('рубль', 'рубля', 'рублей'))} "
        f"{kop:02d} {plural(kop, ('копейка', 'копейки', 'копеек'))}"
    )
