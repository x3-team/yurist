"""Сквозная проверка: прошлое приложение -> шаблон -> новое приложение. Без обращения к API."""

import io
from datetime import date

import pytest
from docx import Document

from make_sample_annex import build

from yurist.models import AnnexInput, Client, Task
from yurist.money import amount_in_words, int_to_words
from yurist.render import bump_number, render_template
from yurist.templater import Markup, Replacement, TaskTable, make_template, replace_in_paragraph

# Так, как разметила бы модель пример из scripts/make_sample_annex.py
MARKUP = Markup(
    client_title="Пример",
    annex_number="7",
    vat_mode="none",
    vat_rate=0,
    task_table=TaskTable(table_id="t0", first_row=1, last_row=3, columns=["n", "name", "deadline", "cost"]),
    replacements=[
        Replacement(paragraph_id="p0", value="7", context="Приложение № 7", variable="annex_number"),
        Replacement(paragraph_id="p2", value="12", context="«12»", variable="annex_date_day"),
        Replacement(paragraph_id="p2", value="сентября", variable="annex_date_month_name"),
        Replacement(paragraph_id="p2", value="2026", context="2026 г.", variable="annex_date_year"),
        Replacement(paragraph_id="p22", value="350 000,00", variable="total"),
        Replacement(paragraph_id="p24", value="14.09.2026", variable="start_date"),
        Replacement(paragraph_id="p24", value="20.10.2026", variable="end_date"),
        Replacement(paragraph_id="p25", value="350 000 (триста пятьдесят тысяч) рублей 00 копеек",
                    variable="total_words"),
        Replacement(paragraph_id="p25", value="Пропущенный фрагмент", variable="total"),
    ],
)


def doc_text(data: bytes) -> str:
    doc = Document(io.BytesIO(data))
    parts = [p.text for p in doc.paragraphs]
    for table in doc.tables:
        for row in table.rows:
            parts.append(" | ".join(c.text for c in row.cells))
    return "\n".join(parts)


@pytest.fixture
def sample(tmp_path) -> bytes:
    return build(tmp_path / "sample.docx").read_bytes()


def test_template_and_render(sample):
    template, report = make_template(sample, MARKUP)
    assert len(report.applied) == 8
    assert report.warnings == ["Не нашёл «Пропущенный фрагмент» в p25, пропущено"]
    assert report.example_tasks[0] == "Разработка дизайн-макета личного кабинета"

    client = Client(id="primer", title="Пример", next_annex_number="8")
    annex = AnnexInput(
        annex_date=date(2026, 11, 3),
        start_date=date(2026, 11, 5),
        end_date=date(2026, 12, 25),
        tasks=[
            Task(name="Доработка отчётов", cost=95000, deadline=date(2026, 11, 30)),
            Task(name="Интеграция с 1С", cost=150000.5, deadline=date(2026, 12, 25)),
        ],
    )
    out, _ = render_template(template, client, annex)
    text = doc_text(out)

    assert "Приложение № 8\nк Договору № 15-04/2026 от 15.04.2026" in text
    assert "«03» ноября 2026 г." in text
    assert "от «15» апреля 2026 г." in text  # дата договора не тронута
    assert "1 | Доработка отчётов | 30.11.2026 | 95 000,00" in text
    assert "2 | Интеграция с 1С | 25.12.2026 | 150 000,50" in text
    assert "Тестирование и запуск" not in text
    assert "245 000,50" in text
    assert "с 05.11.2026 по 25.12.2026" in text
    assert ("245 000 (двести сорок пять тысяч) рублей 50 копеек, НДС не облагается в связи с "
            "применением УСН") in text
    assert "/Иванов И.И./" in text


def test_vat_included(sample):
    template, _ = make_template(sample, MARKUP)
    client = Client(id="x", title="X", vat_mode="included", vat_rate=20)
    out, ctx = render_template(template, client, AnnexInput(tasks=[Task(name="A", cost=120000)]))
    assert ctx["vat"] == "20 000,00"
    assert ctx["subtotal"] == "100 000,00"


def test_words():
    assert int_to_words(1) == "один"
    assert int_to_words(21000) == "двадцать одна тысяча"
    assert int_to_words(2_302_011) == "два миллиона триста две тысячи одиннадцать"
    assert amount_in_words(1001.01) == "1 001 (одна тысяча один) рубль 01 копейка"
    assert amount_in_words(112) == "112 (сто двенадцать) рублей 00 копеек"


def test_bump_number():
    assert bump_number("7") == "8"
    assert bump_number("2026-09") == "2026-10"
    assert bump_number("А") == "А"


def test_replace_across_runs():
    doc = Document()
    p = doc.add_paragraph()
    for chunk in ("Приложение № ", "1", "2", " от"):
        p.add_run(chunk)
    assert replace_in_paragraph(p, "№ 12", "№ {{ annex_number }}")
    assert p.text == "Приложение № {{ annex_number }} от"
