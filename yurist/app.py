"""Веб-сервис: клиенты, загрузка прошлого приложения и выпуск нового.

    uvicorn yurist.app:app --reload
"""

from pathlib import Path
from urllib.parse import quote

import anthropic
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel

from . import parser, render, templater
from .models import AnnexInput, Client

STATIC = Path(__file__).parent / "static"
DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"

app = FastAPI(title="Юрист: приложения к договорам")


def _client_or_404(client_id: str) -> Client:
    try:
        return render.get_client(client_id)
    except KeyError:
        raise HTTPException(404, "Клиент не найден")


def _ai_error(e: Exception) -> HTTPException:
    if isinstance(e, anthropic.AuthenticationError):
        return HTTPException(502, "Не задан или неверен ключ ANTHROPIC_API_KEY")
    if isinstance(e, anthropic.APIError):
        return HTTPException(502, f"Ошибка ИИ: {e}")
    return HTTPException(422, str(e))


def _download(data: bytes, filename: str) -> Response:
    return Response(data, media_type=DOCX,
                    headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}"})


@app.get("/")
def index():
    return FileResponse(STATIC / "index.html")


@app.get("/api/clients")
def clients() -> list[Client]:
    return render.list_clients()


@app.post("/api/clients")
async def add_client(file: UploadFile = File(...), title: str = Form("")):
    """Принимает прошлое приложение клиента (.docx) и делает из него шаблон."""
    if not (file.filename or "").lower().endswith(".docx"):
        raise HTTPException(400, "Нужен файл .docx (если приложение в .doc или PDF, пересохраните его в Word)")
    source = await file.read()
    try:
        template, report = templater.make_template(source)
    except Exception as e:  # noqa: BLE001
        raise _ai_error(e)

    markup = report.markup
    title = title.strip() or markup.client_title
    client = Client(
        id=render.slugify(title),
        title=title,
        vat_mode=markup.vat_mode,
        vat_rate=markup.vat_rate or 20,
        next_annex_number=render.bump_number(markup.annex_number),
        fields=sorted({r.variable for r in report.applied}),
        example_tasks=report.example_tasks,
    )
    render.save_client(client, template=template, source=source)
    return {
        "client": client,
        "found": [{"value": r.value, "variable": r.variable} for r in report.applied],
        "task_table": markup.task_table is not None,
        "warnings": report.warnings,
    }


class ClientUpdate(BaseModel):
    title: str | None = None
    vat_mode: str | None = None
    vat_rate: int | None = None
    next_annex_number: str | None = None


@app.patch("/api/clients/{client_id}")
def update_client(client_id: str, update: ClientUpdate) -> Client:
    client = _client_or_404(client_id)
    client = Client.model_validate(client.model_dump() | update.model_dump(exclude_none=True))
    render.save_client(client)
    return client


@app.get("/api/clients/{client_id}/template")
def download_template(client_id: str):
    client = _client_or_404(client_id)
    return _download(render.template_path(client_id).read_bytes(), f"Шаблон {client.title}.docx")


class ParseRequest(BaseModel):
    text: str


@app.post("/api/clients/{client_id}/parse")
def parse(client_id: str, req: ParseRequest) -> AnnexInput:
    client = _client_or_404(client_id)
    try:
        return parser.parse_text(req.text, client)
    except Exception as e:  # noqa: BLE001
        raise _ai_error(e)


@app.post("/api/clients/{client_id}/generate")
def generate(client_id: str, annex: AnnexInput):
    client = _client_or_404(client_id)
    if not annex.tasks:
        raise HTTPException(400, "Добавьте хотя бы одну задачу")
    data, filename = render.render_annex(client, annex)
    number = annex.annex_number or client.next_annex_number
    if number == client.next_annex_number:
        render.save_client(client.model_copy(update={"next_annex_number": render.bump_number(number)}))
    return _download(data, filename)
