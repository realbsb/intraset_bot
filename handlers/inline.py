from aiogram import Router
from aiogram.types import (
    InlineQuery,
    InlineQueryResultArticle,
    InputTextMessageContent,
)

router = Router()


@router.inline_query()
async def handle_inline(q: InlineQuery):
    """
    Инлайн-вход (пока не подключён).
    В будущем: ссылка → превью, queue → статус очереди, help → справка.
    """
    text = (q.query or "").strip()
    results = []

    if text.lower() == "queue":
        results.append(
            InlineQueryResultArticle(
                id="queue",
                title="Статус очереди",
                description="Показать текущую очередь загрузок",
                input_message_content=InputTextMessageContent(
                    message_text="Очередь: (функционал в разработке)"
                ),
            )
        )
    elif text.lower() == "help":
        results.append(
            InlineQueryResultArticle(
                id="help",
                title="Справка",
                description="Список команд бота",
                input_message_content=InputTextMessageContent(
                    message_text="/start /help /dl <url> ..."
                ),
            )
        )
    else:
        results.append(
            InlineQueryResultArticle(
                id="hint",
                title="Введите ссылку или команду",
                description="YouTube-ссылка, 'queue' или 'help'",
                input_message_content=InputTextMessageContent(
                    message_text="Используйте /start в личке с ботом."
                ),
            )
        )

    await q.answer(results, cache_time=5, is_personal=True)
