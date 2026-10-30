"""Превращает прошлое заполненное приложение клиента в шаблон.

Claude читает документ и говорит, какие фрагменты меняются от приложения к приложению
(номер, даты, суммы, строки таблицы задач). Сами замены делает код: текст, оформление
и всё неизменное остаются как в оригинале.
"""

import copy
import io
import os
import re

import anthropic
from docx import Document
from docx.table import Table
from docx.text.paragraph import Paragraph
from pydantic import BaseModel, Field

from .models import TASK_COLUMNS, VARIABLES, VatMode

MODEL = os.environ.get("YURIST_TEMPLATE_MODEL", "claude-opus-5-5")


class Replacement(BaseModel):
    paragraph_id: str = Field(description="id абзаца, например p12")
    value: str = Field(description="Точный фрагмент, который меняется, например «7»")
    context: str = Field(default="", description="Фрагмент абзаца вокруг value, чтобы место было однозначным, "
                                                 "например «Приложение № 7»; value должно входить в него")
    variable: str = Field(description="Имя переменной из списка")
    capitalize: bool = Field(default=False, description="В оригинале фрагмент с заглавной буквы")


class TaskTable(BaseModel):
    table_id: str = Field(description="id таблицы, например t0")
    first_row: int = Field(description="Индекс первой строки с задачей (с 0, шапка не считается задачей)")
    last_row: int = Field(description="Индекс последней строки с задачей (строка «Итого» не входит)")
    columns: list[str] = Field(description="Для каждой колонки строки задачи: n, name, deadline, cost или keep")


class Markup(BaseModel):
    client_title: str = Field(description="Короткое название заказчика, например «РАТЕП»")
    annex_number: str = Field(description="Номер этого приложения, как в документе")
    vat_mode: VatMode = Field(description="none — без НДС, included — НДС в т.ч., on_top — НДС сверху")
    vat_rate: int = Field(description="Ставка НДС в процентах, 0 если без НДС")
    task_table: TaskTable | None = Field(description="Таблица с перечнем задач, если она есть")
    replacements: list[Replacement]


SYSTEM = """Ты размечаешь утверждённый шаблон приложения к договору. Тебе дан заполненный \
документ прошлого приложения. В новых приложениях меняются только: номер и дата приложения, \
перечень задач с их сроками и стоимостью, сроки работ, итоговая сумма (цифрами и прописью), сумма НДС.
Всё остальное (стороны, реквизиты, номер и дата самого договора, подписи) не меняется — не трогай.

Найди меняющиеся фрагменты и сопоставь каждый с переменной:
{variables}

Строки таблицы задач не размечай через replacements — опиши таблицу в task_table, колонки:
{columns}

Правила:
- value — точная подстрока абзаца, символ в символ. context — чуть более длинная подстрока того же \
абзаца, содержащая value, чтобы не задеть похожие цифры рядом (например «№ 7», «с 14.09.2026»). \
Одна замена на одно место.
- Дату дели на части так, как она записана: «12» сентября 2026 г. -> annex_date_day, \
annex_date_month_name, annex_date_year отдельными заменами; 12.09.2026 -> annex_date целиком.
- Сумму прописью дели так же: «350 000 (триста пятьдесят тысяч) рублей 00 копеек» можно целиком \
total_words, а если формат другой, размечай по частям (total_rub, total_rub_words, total_rub_word ...). \
Если прописью с заглавной буквы — capitalize=true.
- Строка «Итого» в таблице — это replacement с переменной total (или subtotal/vat, если так).
- Дата договора и номер договора — не переменные."""


def _iter_block_items(parent):
    """Абзацы и таблицы в порядке документа."""
    body = parent.element.body if hasattr(parent, "element") else parent._tc
    for child in body.iterchildren():
        if child.tag.endswith("}p"):
            yield Paragraph(child, parent)
        elif child.tag.endswith("}tbl"):
            yield Table(child, parent)


def _unique_cells(row):
    seen, cells = set(), []
    for cell in row.cells:
        if id(cell._tc) not in seen:
            seen.add(id(cell._tc))
            cells.append(cell)
    return cells


def index_document(doc):
    """Нумерует абзацы и таблицы, возвращает текст для модели и словари id -> объект."""
    paragraphs: dict[str, Paragraph] = {}
    tables: dict[str, Table] = {}
    lines: list[str] = []

    def add_par(p):
        pid = f"p{len(paragraphs)}"
        paragraphs[pid] = p
        return pid

    def walk(container, indent=""):
        for block in _iter_block_items(container):
            if isinstance(block, Paragraph):
                pid = add_par(block)
                if block.text.strip():
                    lines.append(f"{indent}[{pid}] {block.text}")
            else:
                tid = f"t{len(tables)}"
                tables[tid] = block
                lines.append(f"{indent}[{tid}] таблица:")
                for r, row in enumerate(block.rows):
                    parts = []
                    for cell in _unique_cells(row):
                        cell_parts = []
                        for p in cell.paragraphs:
                            pid = add_par(p)
                            if p.text.strip():
                                cell_parts.append(f"[{pid}] {p.text}")
                        parts.append(" ".join(cell_parts) or "(пусто)")
                    lines.append(f"{indent}  строка {r}: " + " | ".join(parts))

    walk(doc)
    for section in doc.sections:
        for part in (section.header, section.footer):
            for p in part.paragraphs:
                pid = add_par(p)
                if p.text.strip():
                    lines.append(f"[{pid}] (колонтитул) {p.text}")
    return "\n".join(lines), paragraphs, tables


def replace_in_paragraph(p: Paragraph, old: str, new: str) -> bool:
    """Заменяет первое вхождение фрагмента, сохраняя оформление первого затронутого куска текста."""
    runs = p.runs
    for run in runs:
        if old in run.text:
            run.text = run.text.replace(old, new, 1)
            return True
    full = "".join(r.text for r in runs)
    start = full.find(old)
    if start < 0:
        return False
    end = start + len(old)
    pos, first = 0, True
    for run in runs:
        r_start, r_end = pos, pos + len(run.text)
        pos = r_end
        if r_end <= start or r_start >= end:
            continue
        a, b = max(start, r_start) - r_start, min(end, r_end) - r_start
        run.text = run.text[:a] + (new if first else "") + run.text[b:]
        first = False
    return True


def _set_cell_text(cell, text: str):
    paragraphs = cell.paragraphs
    for extra in paragraphs[1:]:
        extra._p.getparent().remove(extra._p)
    p = paragraphs[0]
    runs = p.runs
    if runs:
        runs[0].text = text
        for r in runs[1:]:
            r._r.getparent().remove(r._r)
    else:
        p.add_run(text)


def apply_task_table(table: Table, spec: TaskTable) -> None:
    rows = table.rows
    first, last = spec.first_row, min(spec.last_row, len(rows) - 1)
    template_row = rows[first]
    for cell, column in zip(_unique_cells(template_row), spec.columns):
        if column in ("n", "name", "deadline", "cost"):
            _set_cell_text(cell, f"{{{{ t.{column} }}}}")
    for row in rows[first + 1:last + 1]:
        row._tr.getparent().remove(row._tr)

    tr = template_row._tr
    tr.addprevious(copy.deepcopy(tr))
    tr.addnext(copy.deepcopy(tr))
    loop_start, _, loop_end = table.rows[first], table.rows[first + 1], table.rows[first + 2]
    for row, tag in ((loop_start, "{%tr for t in tasks %}"), (loop_end, "{%tr endfor %}")):
        cells = _unique_cells(row)
        _set_cell_text(cells[0], tag)
        for cell in cells[1:]:
            _set_cell_text(cell, "")


_VAR_RE = re.compile(r"^(annex_number|(annex_date|start_date|end_date)(_day|_month_name|_month|_year)?|"
                     r"(total|vat|subtotal)(_rub|_kop|_rub_words|_rub_word|_kop_word|_words)?)$")


def ask_markup(document_text: str) -> Markup:
    variables = "\n".join(f"- {k}: {v}" for k, v in VARIABLES.items())
    columns = "\n".join(f"- {k}: {v}" for k, v in TASK_COLUMNS.items())
    api = anthropic.Anthropic()
    response = api.messages.parse(
        model=MODEL,
        max_tokens=16000,
        output_config={"effort": "high"},
        system=SYSTEM.format(variables=variables, columns=columns),
        messages=[{"role": "user", "content": f"Документ:\n\n{document_text}"}],
        output_format=Markup,
    )
    if response.stop_reason == "refusal" or response.parsed_output is None:
        raise ValueError("Не удалось разобрать документ")
    return response.parsed_output


class TemplateResult(BaseModel):
    markup: Markup
    applied: list[Replacement]
    warnings: list[str]
    example_tasks: list[str]


def make_template(source: bytes, markup: Markup | None = None) -> tuple[bytes, TemplateResult]:
    """Возвращает .docx шаблона и отчёт о том, что было размечено."""
    doc = Document(io.BytesIO(source))
    text, paragraphs, tables = index_document(doc)
    markup = markup or ask_markup(text)

    applied, warnings = [], []
    for rep in markup.replacements:
        if not _VAR_RE.match(rep.variable):
            warnings.append(f"Неизвестная переменная {rep.variable} для «{rep.value}», пропущено")
            continue
        p = paragraphs.get(rep.paragraph_id)
        tag = f"{{{{ {rep.variable}{'|capfirst' if rep.capitalize else ''} }}}}"
        context = rep.context if rep.value in rep.context else rep.value
        if p is None or not replace_in_paragraph(p, context, context.replace(rep.value, tag, 1)):
            warnings.append(f"Не нашёл «{context}» в {rep.paragraph_id}, пропущено")
            continue
        applied.append(rep)

    example_tasks: list[str] = []
    spec = markup.task_table
    if spec and spec.table_id in tables:
        table = tables[spec.table_id]
        if "name" in spec.columns:
            col = spec.columns.index("name")
            for row in table.rows[spec.first_row:spec.last_row + 1]:
                cells = _unique_cells(row)
                if col < len(cells):
                    example_tasks.append(cells[col].text.strip())
        apply_task_table(table, spec)
    else:
        warnings.append("Таблица задач не найдена: задачи в документ не попадут")

    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue(), TemplateResult(markup=markup, applied=applied, warnings=warnings,
                                          example_tasks=[t for t in example_tasks if t][:10])
