"""Клиенты, их шаблоны и заполнение шаблона новыми вводными."""

import io
import json
import os
import re
from pathlib import Path

import jinja2
from docxtpl import DocxTemplate

from .models import AnnexInput, Client, build_context

DATA_DIR = Path(os.environ.get("YURIST_DATA", Path(__file__).resolve().parent.parent / "data"))


def _client_dir(client_id: str) -> Path:
    return DATA_DIR / "clients" / client_id


def slugify(title: str) -> str:
    table = str.maketrans("абвгдеёжзийклмнопрстуфхцчшщъыьэюя",
                          "abvgdeejzijklmnoprstufhccss_y_eua")
    slug = re.sub(r"[^a-z0-9]+", "-", title.lower().translate(table)).strip("-")
    return slug or "client"


def list_clients() -> list[Client]:
    root = DATA_DIR / "clients"
    if not root.exists():
        return []
    return [Client(**json.loads(p.read_text(encoding="utf-8")))
            for p in sorted(root.glob("*/client.json"))]


def get_client(client_id: str) -> Client:
    path = _client_dir(client_id) / "client.json"
    if not path.exists():
        raise KeyError(client_id)
    return Client(**json.loads(path.read_text(encoding="utf-8")))


def save_client(client: Client, template: bytes | None = None, source: bytes | None = None) -> None:
    folder = _client_dir(client.id)
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "client.json").write_text(client.model_dump_json(indent=2), encoding="utf-8")
    if template is not None:
        (folder / "template.docx").write_bytes(template)
    if source is not None:
        (folder / "source.docx").write_bytes(source)


def template_path(client_id: str) -> Path:
    return _client_dir(client_id) / "template.docx"


def _jinja_env() -> jinja2.Environment:
    env = jinja2.Environment(autoescape=True)
    env.filters["capfirst"] = lambda s: str(s)[:1].upper() + str(s)[1:]
    return env


def render_template(template: Path | bytes, client: Client, annex: AnnexInput) -> tuple[bytes, dict]:
    context = build_context(client, annex)
    src = io.BytesIO(template) if isinstance(template, bytes) else template
    doc = DocxTemplate(src)
    doc.render(context, jinja_env=_jinja_env())
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue(), context


def render_annex(client: Client, annex: AnnexInput) -> tuple[bytes, str]:
    """Возвращает содержимое .docx и имя файла."""
    data, context = render_template(template_path(client.id), client, annex)
    filename = f"Приложение №{context['annex_number']} {client.title}.docx"
    return data, re.sub(r'[\\/:*?"<>|]', "-", filename)


def bump_number(number: str) -> str:
    """«7» -> «8», «2026-07» -> «2026-08»; если чисел нет, оставляет как есть."""
    m = re.search(r"(\d+)(?!.*\d)", number)
    if not m:
        return number
    digits = m.group(1)
    return number[:m.start()] + str(int(digits) + 1).zfill(len(digits)) + number[m.end():]
