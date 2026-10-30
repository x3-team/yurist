"""Разбор свободного текста («надиктовал как есть») в поля приложения с помощью Claude."""

import os
from datetime import date

import anthropic

from .models import AnnexInput, Client

MODEL = os.environ.get("YURIST_PARSE_MODEL", "claude-sonnet-5-5")

SYSTEM = """Ты помощник юриста. Пользователь своими словами (часто это расшифровка голоса) \
описывает новое приложение к договору: перечень задач, их стоимость, сроки, номер и дату приложения.
Извлеки данные в структуру. Правила:
- Каждая отдельная работа — отдельная задача. Наименование пиши деловым языком, как в договоре, \
с заглавной буквы, без лишних слов («сделать лендинг» -> «Разработка лендинга»), но не выдумывай \
содержание, которого не было.
- Стоимость — число в рублях. «150к», «сто пятьдесят тысяч», «1,2 млн» переводи в число.
- Даты переводи в ISO (ГГГГ-ММ-ДД). Относительные даты («до конца ноября», «через две недели») \
считай от сегодняшней даты. Если дата не названа — оставь пустой, не придумывай.
- Если общая сумма названа, а по задачам нет — не дели её сам, оставь как одну задачу или \
верни задачи с 0 там, где цены нет.
- Номер приложения указывай только если он назван."""


def parse_text(text: str, client: Client, today: date | None = None) -> AnnexInput:
    today = today or date.today()
    api = anthropic.Anthropic()
    response = api.messages.parse(
        model=MODEL,
        max_tokens=16000,
        output_config={"effort": "low"},
        system=SYSTEM,
        messages=[{
            "role": "user",
            "content": (
                f"Сегодня: {today.isoformat()}\n"
                f"Клиент: {client.title}\n"
                f"Так задачи названы в прошлом приложении (держись этого стиля): "
                f"{'; '.join(client.example_tasks) or 'нет примеров'}\n\n"
                f"Текст пользователя:\n{text}"
            ),
        }],
        output_format=AnnexInput,
    )
    if response.stop_reason == "refusal" or response.parsed_output is None:
        raise ValueError("Не удалось разобрать текст, заполните поля вручную")
    return response.parsed_output
