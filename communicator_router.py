import os
import json
import logging
import asyncio
from typing import List

from aiogram import Router, F, flags
from aiogram.filters import Command
from aiogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from aiogram.exceptions import TelegramBadRequest


from config import config

# Здесь вы импортируете свои модули (аналог db.php, openai.php, vector_search.php)
# Предположим, у вас есть такие функции:
from db import (
    getUserByTelegramId,
    createUser,
    saveChatMessage,
    getLastMessages
)
from vector_search import vectorSearch
from openai_module import (
    get_gpt_chat_with_history,
    send_to_whisper
)

from data_manager import check_and_add_user

communicator_router = Router()

    
 # Из кода следует, что ищем упоминание этого.


# ======================
# Вспомогательные функции
# ======================

async def notify_manager(
    bot,
    manager_chat_id: int,
    from_username: str,
    original_chat_id: int,
    text: str,
    context: str = ""
):
    """
    Аналог notifyManager(...) из PHP.
    Уведомляем менеджера сообщением «Упоминание менеджера! Автор: ...».
    """
    display_name = f"@{from_username}" if from_username else "(без username)"

    msg = (
        "Упоминание менеджера!\n"
        f"Автор: {display_name} (chat_id: {original_chat_id})\n\n"
        f"Текст:\n{text}"
    )
    if context:
        msg += "\n\n--*Контекст (последние сообщения)*--:\n" + context

    try:
        await bot.send_message(chat_id=manager_chat_id, text=msg)
    except TelegramBadRequest as e:
        logging.error(f"Ошибка при уведомлении менеджера: {e}")


def convertDoubleAsterisksToTelegram(text: str) -> str:
    """
    Преобразуем **bold** => *bold* (Телеграм Markdown),
    аналог convertDoubleAsterisksToTelegram()
    """
    import re
    pattern = r"\*\*(.*?)\*\*"
    replacement = r"*\1*"
    return re.sub(pattern, replacement, text, flags=re.DOTALL)


def extractButtonsFromGptReply(gptReply: str) -> List[dict]:
    """
    Ищем блок [BUTTONS_JSON]{...}[/BUTTONS_JSON], чтобы извлечь массив кнопок (JSON).
    """
    import re
    pattern = r"\[BUTTONS_JSON\](.*?)\[/BUTTONS_JSON\]"
    match = re.search(pattern, gptReply, flags=re.DOTALL)
    if match:
        json_text = match.group(1).strip()
        try:
            data = json.loads(json_text)
            if "buttons" in data and isinstance(data["buttons"], list):
                return data["buttons"]
        except json.JSONDecodeError:
            pass
    return []


async def download_telegram_voice(bot, file_id: str) -> str | None:
    """
    Аналог ваших функций telegramGetFilePath + downloadTelegramFile,
    но в стиле Python. Возвращает локальный путь к скачанному файлу.
    """
    # Получаем file_path
    try:
        file_info = await bot.get_file(file_id)
    except TelegramBadRequest as e:
        logging.error(f"Не удалось получить info по file_id={file_id}: {e}")
        return None

    if not file_info.file_path:
        return None

    # Скачиваем
    dir_path = os.path.join(os.path.dirname(__file__), "tmp_voices")
    os.makedirs(dir_path, exist_ok=True)
    local_filename = os.path.join(dir_path, os.path.basename(file_info.file_path))

    await bot.download_file(file_path=file_info.file_path, destination=local_filename)
    return local_filename


def checkMentionManager(text: str) -> bool:
    """
    Проверяем, есть ли в тексте упоминание MANAGER_USERNAME
    """
    return config.MANAGER_USERNAME.lower() in text.lower()


# ======================
# Хендлер на колбэки (инлайн-кнопки)
# ======================
@communicator_router.callback_query()
async def handle_callback_query(callback_query: CallbackQuery):
    """
    Аналог блока 1) в PHP: if (isset($updateData["callback_query"])) { ... }
    """
    callback_data = callback_query.data  # строка callback_data
    callback_id = callback_query.id
    from_chat_id = callback_query.message.chat.id
    from_username = callback_query.from_user.username or ""

    # Убираем «загрузка...»
    await callback_query.answer(text="Ок!")  # аналог answerCallbackQuery

    # Определяем / создаём пользователя
    user = getUserByTelegramId(from_chat_id)
    if not user:
        createUser(from_chat_id, from_username)
        user = getUserByTelegramId(from_chat_id)
    user_id = user["id"]

    # Сохраняем «user-сообщение» о нажатии
    user_msg = f"Нажата кнопка (callback_data): {callback_data}"
    saveChatMessage(user_id, "user", user_msg, "text", None)

    # RAG
    # chunks = vectorSearch(user_msg, top_k=3)
    # retrieved = ""
    # for i, c in enumerate(chunks):
    #     retrieved += f"\n--- Фрагмент #{i+1}(score={c['score']:.4f})---\n{c['chunk_text']}\n"

    # GPT
    # gptReply = get_gpt_chat_with_history(user_id, 15, system_instructions=f"RAG:\n{retrieved}")
    gptReply = get_gpt_chat_with_history(user_id, 15, system_instructions=f"RAG:")
    saveChatMessage(user_id, "assistant", gptReply, "text", None)

    # Проверяем упоминание менеджера
    if checkMentionManager(gptReply):
        last_msgs = getLastMessages(user_id, 3)
        context = ""
        for m in last_msgs:
            context += f"[{m['role']}] {m['content']}\n"
        await notify_manager(callback_query.bot, config.MANAGER_CHAT_ID, from_username, from_chat_id, gptReply, context)

    # Извлекаем кнопки
    buttonsData = extractButtonsFromGptReply(gptReply)
    # Удаляем сам блок [BUTTONS_JSON]...[/BUTTONS_JSON] из текста
    import re
    gptReplyClean = re.sub(r"\[BUTTONS_JSON\].*?\[/BUTTONS_JSON\]", "", gptReply, flags=re.DOTALL)
    # Преобразуем **bold** => *bold* для Telegram
    gptReplyClean = convertDoubleAsterisksToTelegram(gptReplyClean)

    # Формируем Inline Keyboard
    inline_keyboard = []
    if buttonsData:
        for btn in buttonsData:
            txt = btn.get("text")
            cb = btn.get("callback")
            if txt and cb:
                inline_keyboard.append([InlineKeyboardButton(text=txt, callback_data=cb)])

    # Отправляем ответ
    await callback_query.message.answer(
        text=gptReplyClean,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=inline_keyboard) if inline_keyboard else None
    )


# ======================
# Хендлер для голосовых сообщений
# ======================
@communicator_router.message(F.voice)
async def handle_voice_message(message: Message):
    """
    Аналог обработки voice из PHP-кода
    """
    bot = message.bot
    chat_id = message.chat.id
    userName = message.from_user.username or ""

    # Печатаем "typing..."
    # await message.answer_chat_action(ChatAction.TYPING)
    # Эмулируем "⏳ ..."
    await message.answer("⏳ ...")

    # Находим / создаём пользователя
    user = getUserByTelegramId(chat_id)
    if not user:
        createUser(chat_id, userName)
        user = getUserByTelegramId(chat_id)
    user_id = user["id"]

    # Скачиваем voice
    file_id = message.voice.file_id
    local_path = await download_telegram_voice(bot, file_id)
    if not local_path:
        await message.answer("Не удалось скачать voice-файл")
        return

    # Отправляем в Whisper (as в PHP sendToWhisper($loc))
    stt_res = send_to_whisper(local_path)
    if "error" in stt_res:
        await message.answer(f"Ошибка распознавания: {stt_res['error']}")
        return

    recText = stt_res.get("text", "")
    # Сохраняем user-message (voice -> распознанный текст)
    saveChatMessage(user_id, "user", recText, "voice", local_path)

    # Упоминание менеджера?
    if checkMentionManager(recText):
        last_msgs = getLastMessages(user_id, 3)
        context = "\n".join(f"[{m['role']}] {m['content']}" for m in last_msgs)
        await notify_manager(bot, config.MANAGER_CHAT_ID, userName, chat_id, recText, context)

    # RAG
    chunks = vectorSearch(recText, 3)
    retrieved = ""
    for i, c in enumerate(chunks):
        retrieved += f"\n--- Фрагмент #{i+1}(score={c['score']:.4f})---\n{c['chunk_text']}\n"

    # GPT
    gptReply = get_gpt_chat_with_history(user_id, 15, system_instructions=f"RAG:\n{retrieved}")
    saveChatMessage(user_id, "assistant", gptReply, "text", None)

    if checkMentionManager(gptReply):
        last_msgs = getLastMessages(user_id, 3)
        context = "\n".join(f"[{m['role']}] {m['content']}" for m in last_msgs)
        await notify_manager(bot, config.MANAGER_CHAT_ID, userName, chat_id, gptReply, context)

    # Кнопки
    buttonsData = extractButtonsFromGptReply(gptReply)
    import re
    gptReplyClean = re.sub(r"\[BUTTONS_JSON\].*?\[/BUTTONS_JSON\]", "", gptReply, flags=re.DOTALL)
    gptReplyClean = convertDoubleAsterisksToTelegram(gptReplyClean)

    inline_keyboard = []
    for btn in buttonsData:
        text = btn.get("text")
        cb = btn.get("callback")
        if text and cb:
            inline_keyboard.append([InlineKeyboardButton(text=text, callback_data=cb)])

    await message.answer(
        text=gptReplyClean,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=inline_keyboard) if inline_keyboard else None
    )


# ======================
# Хендлер для текстовых сообщений
# ======================
@communicator_router.message(F.text)
async def handle_text_message(message: Message):
    """
    Аналог обычных текстовых сообщений из PHP:
    """
    bot = message.bot
    chat_id = message.chat.id
    text = message.text
    userName = message.from_user.username or ""
    await asyncio.sleep(3)

    "typing..." + "⏳"
    # await message.answer_chat_action(ChatActions.TYPING)
    await message.answer("⏳ ...")

    # user
    user_id = await check_and_add_user(chat_id, userName) 

    # Сохраняем user-сообщение
    # saveChatMessage(user_id, "user", text, "text", None)

    # Проверяем упоминание менеджера
    if checkMentionManager(text):
        last_msgs = getLastMessages(user_id, 3)
        context = "\n".join(f"[{m['role']}] {m['content']}" for m in last_msgs)
        await notify_manager(bot, config.MANAGER_CHAT_ID, userName, chat_id, text, context)

    # RAG
    chunks = vectorSearch(text, 3)
    retrieved = ""
    for i, c in enumerate(chunks):
        retrieved += f"\n--- Фрагмент #{i+1}(score={c['score']:.4f})---\n{c['chunk_text']}\n"

    # GPT
    gptReply = get_gpt_chat_with_history(user_id, 15, system_instructions=f"RAG:\n{retrieved}")
    saveChatMessage(user_id, "assistant", gptReply, "text", None)

    # Упоминание менеджера в gptReply?
    if checkMentionManager(gptReply):
        last_msgs = getLastMessages(user_id, 3)
        context = "\n".join(f"[{m['role']}] {m['content']}" for m in last_msgs)
        await notify_manager(bot, config.MANAGER_CHAT_ID, userName, chat_id, gptReply, context)

    # Кнопки
    import re
    buttonsData = extractButtonsFromGptReply(gptReply)
    gptReplyClean = re.sub(r"\[BUTTONS_JSON\].*?\[/BUTTONS_JSON\]", "", gptReply, flags=re.DOTALL)
    gptReplyClean = convertDoubleAsterisksToTelegram(gptReplyClean)

    inline_keyboard = []
    for btn in buttonsData:
        bt_text = btn.get("text")
        cb = btn.get("callback")
        if bt_text and cb:
            inline_keyboard.append([InlineKeyboardButton(text=bt_text, callback_data=cb)])

    await message.answer(
        text=gptReplyClean,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=inline_keyboard) if inline_keyboard else None
    )
