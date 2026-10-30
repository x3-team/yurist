"""Данные приложения к договору и переменные шаблона."""

from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field

from .money import format_amount, int_to_words, plural, amount_in_words, to_decimal

VatMode = Literal["none", "included", "on_top"]


class Task(BaseModel):
    name: str = Field(description="Наименование работы/задачи, как оно пойдёт в таблицу")
    cost: float = Field(description="Стоимость задачи в рублях")
    deadline: date | None = Field(default=None, description="Срок выполнения задачи, если назван")


class AnnexInput(BaseModel):
    """То, что меняется от приложения к приложению."""

    annex_number: str | None = Field(default=None, description="Номер приложения, если назван")
    annex_date: date | None = Field(default=None, description="Дата приложения, если названа")
    start_date: date | None = Field(default=None, description="Дата начала работ")
    end_date: date | None = Field(default=None, description="Дата окончания работ")
    tasks: list[Task] = Field(default_factory=list)


class Client(BaseModel):
    """Клиент: его шаблон лежит рядом, в data/clients/<id>/template.docx."""

    id: str
    title: str
    vat_mode: VatMode = "none"
    vat_rate: int = 20
    next_annex_number: str = "1"
    example_tasks: list[str] = Field(default_factory=list, description="Задачи из прошлого приложения")
    fields: list[str] = Field(default_factory=list, description="Какие переменные нашлись в шаблоне")


_MONTHS = ["января", "февраля", "марта", "апреля", "мая", "июня", "июля", "августа",
           "сентября", "октября", "ноября", "декабря"]


def fmt_date(d: date | None) -> str:
    return d.strftime("%d.%m.%Y") if d else ""


def date_vars(prefix: str, d: date | None) -> dict[str, str]:
    return {
        prefix: fmt_date(d),
        f"{prefix}_day": f"{d.day:02d}" if d else "",
        f"{prefix}_month_name": _MONTHS[d.month - 1] if d else "",
        f"{prefix}_month": f"{d.month:02d}" if d else "",
        f"{prefix}_year": str(d.year) if d else "",
    }


def money_vars(prefix: str, value: Decimal) -> dict[str, str]:
    rub, kop = divmod(int(to_decimal(value) * 100), 100)
    return {
        prefix: format_amount(value),
        f"{prefix}_rub": f"{rub:,}".replace(",", " "),
        f"{prefix}_kop": f"{kop:02d}",
        f"{prefix}_rub_words": int_to_words(rub),
        f"{prefix}_rub_word": plural(rub, ("рубль", "рубля", "рублей")),
        f"{prefix}_kop_word": plural(kop, ("копейка", "копейки", "копеек")),
        f"{prefix}_words": amount_in_words(value),
    }


# Описание переменных для разметки шаблона (пример значения -> смысл).
VARIABLES = {
    "annex_number": "номер приложения, «7»",
    "annex_date": "дата приложения, «12.09.2026»",
    "annex_date_day / _month_name / _month / _year": "части даты приложения: «12», «сентября», «09», «2026»",
    "start_date (+ _day/_month_name/_month/_year)": "дата начала работ",
    "end_date (+ _day/_month_name/_month/_year)": "дата окончания работ",
    "total": "итоговая сумма к оплате, «350 000,00»",
    "total_rub / total_kop": "рубли и копейки итога цифрами: «350 000», «00»",
    "total_rub_words": "рубли итога прописью: «триста пятьдесят тысяч»",
    "total_rub_word / total_kop_word": "«рублей» / «копеек» в нужном падеже",
    "total_words": "итог целиком: «350 000 (триста пятьдесят тысяч) рублей 00 копеек»",
    "vat (+ _rub/_kop/_rub_words/_rub_word/_kop_word/_words)": "сумма НДС",
    "subtotal (+ те же суффиксы)": "сумма без НДС (если НДС сверху)",
}

TASK_COLUMNS = {
    "n": "порядковый номер",
    "name": "наименование работы",
    "deadline": "срок задачи «30.09.2026»",
    "cost": "стоимость задачи «120 000,00»",
    "keep": "колонка не меняется (оставить как есть, например «шт.» или «1»)",
}


def build_context(client: Client, annex: AnnexInput) -> dict:
    """Готовит переменные для шаблона. Все суммы считаются здесь, а не моделью."""
    total = sum((to_decimal(t.cost) for t in annex.tasks), Decimal("0"))
    rate = Decimal(client.vat_rate)
    if client.vat_mode == "included":
        vat = (total * rate / (100 + rate)).quantize(Decimal("0.01"))
        subtotal, grand_total = total - vat, total
    elif client.vat_mode == "on_top":
        vat = (total * rate / 100).quantize(Decimal("0.01"))
        subtotal, grand_total = total, total + vat
    else:
        vat, subtotal, grand_total = Decimal("0"), total, total

    ctx: dict = {"annex_number": annex.annex_number or client.next_annex_number}
    ctx |= date_vars("annex_date", annex.annex_date or date.today())
    ctx |= date_vars("start_date", annex.start_date)
    ctx |= date_vars("end_date", annex.end_date)
    ctx |= money_vars("total", grand_total)
    ctx |= money_vars("vat", vat)
    ctx |= money_vars("subtotal", subtotal)
    ctx["tasks"] = [
        {"n": i, "name": t.name, "cost": format_amount(t.cost), "deadline": fmt_date(t.deadline)}
        for i, t in enumerate(annex.tasks, 1)
    ]
    return ctx
