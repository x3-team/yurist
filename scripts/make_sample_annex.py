"""Создаёт пример заполненного приложения к договору (для тестов и демонстрации).

Это обычный документ без разметки, такой же, как реальное прошлое приложение клиента:
сервис должен сам найти в нём, что меняется.

    python scripts/make_sample_annex.py [путь.docx]
"""

import sys
from pathlib import Path

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Pt

DEFAULT_OUT = Path(__file__).resolve().parent.parent / "examples" / "sample_annex.docx"


def para(doc, text, align=None, bold=False):
    p = doc.add_paragraph()
    run = p.add_run(text)
    run.bold = bold
    if align is not None:
        p.alignment = align
    return p


def build(out: Path) -> Path:
    doc = Document()
    style = doc.styles["Normal"]
    style.font.name = "Times New Roman"
    style.font.size = Pt(12)

    para(doc, "Приложение № 7\nк Договору № 15-04/2026 от 15.04.2026", WD_ALIGN_PARAGRAPH.RIGHT)
    para(doc, "ЗАДАНИЕ НА ВЫПОЛНЕНИЕ РАБОТ", WD_ALIGN_PARAGRAPH.CENTER, bold=True)
    para(doc, "г. Москва\t\t\t\t\t\t«12» сентября 2026 г.")
    para(doc, "АО «Пример», именуемое в дальнейшем «Заказчик», и ООО «Исполнитель», именуемое в "
              "дальнейшем «Исполнитель», составили настоящее Приложение к Договору № 15-04/2026 "
              "от «15» апреля 2026 г. о нижеследующем:")
    para(doc, "1. Исполнитель обязуется выполнить следующие работы:")

    rows = [
        ("1", "Разработка дизайн-макета личного кабинета", "30.09.2026", "120 000,00"),
        ("2", "Вёрстка и интеграция личного кабинета", "15.10.2026", "180 000,00"),
        ("3", "Тестирование и запуск", "20.10.2026", "50 000,00"),
    ]
    table = doc.add_table(rows=1, cols=4)
    table.style = "Table Grid"
    for cell, text in zip(table.rows[0].cells, ["№", "Наименование работ", "Срок", "Стоимость, руб."]):
        cell.text = text
        cell.paragraphs[0].runs[0].bold = True
    for row in rows:
        for cell, text in zip(table.add_row().cells, row):
            cell.text = text
    total = table.add_row().cells
    total[0].merge(total[2]).text = "Итого:"
    total[3].text = "350 000,00"

    para(doc, "")
    para(doc, "2. Сроки выполнения работ: с 14.09.2026 по 20.10.2026.")
    para(doc, "3. Стоимость работ по настоящему Приложению составляет 350 000 (триста пятьдесят тысяч) "
              "рублей 00 копеек, НДС не облагается в связи с применением УСН.")
    para(doc, "4. Настоящее Приложение является неотъемлемой частью Договора и составлено в двух "
              "экземплярах, имеющих одинаковую юридическую силу, по одному для каждой из Сторон.")
    para(doc, "")
    sign = doc.add_table(rows=2, cols=2)
    sign.rows[0].cells[0].text = "Заказчик:\nАО «Пример»"
    sign.rows[0].cells[1].text = "Исполнитель:\nООО «Исполнитель»"
    sign.rows[1].cells[0].text = "\n_______________ /Иванов И.И./"
    sign.rows[1].cells[1].text = "\n_______________ /Петров П.П./"

    out.parent.mkdir(parents=True, exist_ok=True)
    doc.save(out)
    return out


if __name__ == "__main__":
    print(build(Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_OUT))
