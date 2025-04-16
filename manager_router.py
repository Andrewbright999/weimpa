import json
import time
import os
import logging
from typing import List

from aiogram import Router, F
from aiogram.types import Message, ChatMemberUpdated
from aiogram.enums import ChatMemberStatus
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import ChatMemberUpdatedFilter

# aiogram 3.x: фильтры chat_member_updated
from aiogram.filters.chat_member_updated import JOIN_TRANSITION, LEAVE_TRANSITION

# Ваши модули
from config import config
from google_sheets import (
    user_exists, add_user_row, add_message_row,
    mark_message_as_spam
)
from openai_module import is_spam


manager_router = Router()

# -----------------------------------------
# Вспомогательные функции
# -----------------------------------------

def get_active_welcome() -> dict | None:
    """
    Считываем текущее приветственное сообщение (если есть) из файла.
    Аналог PHP: getActiveWelcome()
    """
    path = config.CURRENT_WELCOME_FILE
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else None
    except:
        return None


def save_active_welcome(data: dict):
    """
    Сохраняем текущее приветственное сообщение.
    Аналог PHP: saveActiveWelcome()
    """
    path = config.CURRENT_WELCOME_FILE
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f)


async def create_welcome_message(bot, chat_id: int, usernames: List[str]) -> int | None:
    """
    Создаём новое приветственное сообщение. 
    Аналог PHP: createWelcomeMessage()
    Возвращаем message_id.
    """
    from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

    mentions = ", ".join(usernames)
    # Заменяем {users} в шаблоне
    text = config.WELCOME_TEXT.replace("{users}", mentions)

    markup = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text="Сгенерировать видео",
                url="https://t.me/sp_ai_montage_bot"
            )
        ]
    ])

    try:
        msg = await bot.send_message(chat_id=chat_id, text=text, reply_markup=markup)
        return msg.message_id if msg else None
    except TelegramBadRequest as e:
        logging.error(f"Ошибка при отправке приветствия: {e}")
        return None


async def update_welcome_message(bot, chat_id: int, message_id: int,
                                 old_users: List[str], new_users: List[str]) -> List[str]:
    """
    Обновляем текущее приветственное сообщение, добавляя новых участников.
    Аналог PHP: updateWelcomeMessage()
    """
    from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

    merged = list(set(old_users + new_users))
    mentions = ", ".join(merged)
    text = config.WELCOME_TEXT.replace("{users}", mentions)

    markup = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text="Сгенерировать видео",
                url="https://t.me/sp_ai_montage_bot"
            )
        ]
    ])

    try:
        await bot.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text=text,
            reply_markup=markup
        )
    except TelegramBadRequest as e:
        logging.error(f"Ошибка при редактировании приветствия: {e}")

    return merged


async def delete_welcome_message(bot, chat_id: int, message_id: int):
    """
    Удаляем приветственное сообщение.
    Аналог PHP: deleteWelcomeMessage()
    """
    try:
        await bot.delete_message(chat_id, message_id)
    except TelegramBadRequest as e:
        logging.error(f"Ошибка при удалении приветствия: {e}")

    # Чистим файл
    path = config.CURRENT_WELCOME_FILE
    if os.path.exists(path):
        with open(path, "w", encoding="utf-8") as f:
            f.write("")


async def notify_manager(bot, text: str):
    """
    Отправляем уведомление менеджеру (админу).
    Аналог PHP: notifyManager()
    """
    if config.MANAGER_CHAT_ID:
        try:
            await bot.send_message(chat_id=config.MANAGER_CHAT_ID, text=text)
        except TelegramBadRequest as e:
            logging.error(f"Ошибка при уведомлении менеджера: {e}")


def schedule_message_for_deletion(chat_id: int, message_id: int, delay: int = 60):
    """
    Если хотите сохранять сообщение для дальнейшего удаления через N секунд/минут 
    (аналог PHP: toDelete.json). Вызывается где нужно.
    """
    path = config.TO_DELETE_FILE
    now = time.time()
    entry = {
        "chat_id": chat_id,
        "message_id": message_id,
        "delete_after": now + delay
    }

    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, list):
                data = []
        except:
            data = []
    else:
        data = []

    data.append(entry)

    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f)


# -----------------------------------------
# Обработка новых участников (JOIN)
# -----------------------------------------
async def handle_new_members(bot, chat_id: int, new_members: List, reason: str = ""):
    """
    Аналог PHP: handleNewMembers()
    """
    for member in new_members:
        user_id = member.id
        username = member.username or ""
        first_name = member.first_name or ""
        last_name = member.last_name or ""
        display_user = f"@{username}" if username else f"{first_name} {last_name}".strip()

        msg = (
            f"Пользователь {display_user} ({user_id}) только что "
            f"ПРИСОЕДИНИЛСЯ к чату {chat_id}.\n"
            f"Событие: {reason}"
        )
        await notify_manager(bot, msg)

    # Список имён
    new_usernames = []
    for m in new_members:
        if m.username:
            new_usernames.append(f"@{m.username}")
        else:
            fn = m.first_name or ""
            ln = m.last_name or ""
            new_usernames.append(f"{fn} {ln}".strip())

    # Логика приветствия
    active = get_active_welcome()
    now = time.time()

    if active:
        created_at = active.get("created_at", 0)
        old_msg_id = active.get("message_id")
        mentioned = active.get("mentioned", [])
        old_chat_id = active.get("chat_id")

        if (now - created_at) > config.WELCOME_LIFETIME or (old_chat_id != chat_id):
            # Удаляем старое (если есть), создаём новое
            if old_msg_id and old_chat_id:
                await delete_welcome_message(bot, old_chat_id, old_msg_id)
            new_id = await create_welcome_message(bot, chat_id, new_usernames)
            if new_id:
                data = {
                    "chat_id": chat_id,
                    "message_id": new_id,
                    "created_at": now,
                    "mentioned": new_usernames
                }
                save_active_welcome(data)
        else:
            # Обновляем старое
            if old_msg_id:
                merged = await update_welcome_message(
                    bot, chat_id, old_msg_id, mentioned, new_usernames
                )
                data = {
                    "chat_id": chat_id,
                    "message_id": old_msg_id,
                    "created_at": created_at,
                    "mentioned": merged
                }
                save_active_welcome(data)
            else:
                # Нет message_id — просто создаём
                new_id = await create_welcome_message(bot, chat_id, new_usernames)
                if new_id:
                    data = {
                        "chat_id": chat_id,
                        "message_id": new_id,
                        "created_at": now,
                        "mentioned": new_usernames
                    }
                    save_active_welcome(data)
    else:
        # Нет активного приветствия
        new_id = await create_welcome_message(bot, chat_id, new_usernames)
        if new_id:
            data = {
                "chat_id": chat_id,
                "message_id": new_id,
                "created_at": now,
                "mentioned": new_usernames
            }
            save_active_welcome(data)


# -----------------------------------------
# Обработка ухода (LEAVE)
# -----------------------------------------
async def handle_member_left(bot, chat_id: int, user, reason: str = ""):
    """
    Аналог PHP: handleMemberLeft()
    """
    user_id = user.username
    username = user.username or ""
    first_name = user.first_name or ""
    last_name = user.last_name or ""
    display_user = f"@{username}" if username else f"{first_name} {last_name}".strip()

    msg = (
        f"Пользователь {display_user} ({user_id}) "
        f"покинул чат {chat_id}.\n"
        f"Событие: {reason}"
    )
    await notify_manager(bot, msg)


# -----------------------------------------
# ХЕНДЛЕРЫ РОУТЕРА
# -----------------------------------------


@manager_router.message(F.new_chat_members)
async def on_new_chat_members_handler(message: Message):
    """
    Старый формат прихода пользователей: message.new_chat_members.
    """
    # handleNewMembers
    chat_id = message.chat.id
    new_members = message.new_chat_members
    reason = "old format: new_chat_members"

    # Пример: вы можете сначала вызвать "delete_old_messages" (если логика требует),
    # но обычно это делается через schedule или в начале каждого хендлера.
    await handle_new_members(
        bot=message.bot,
        chat_id=chat_id,
        new_members=new_members,
        reason=reason
    )
    

@manager_router.message(F.left_chat_member)
async def on_left_chat_member_handler(message: Message):
    """
    Старый формат ухода пользователя: message.left_chat_member.
    """
    chat_id = message.chat.id
    user_left = message.left_chat_member
    reason = "old format: left_chat_member"
    await handle_member_left(message.bot, chat_id, user_left, reason)
    
    
    
# @manager_router.chat_member(ChatMemberUpdatedFilter(member_status_changed=JOIN_TRANSITION))
# async def new_member_joined_chat_member(event: ChatMemberUpdated):
#     """
#     Новый формат прихода: chat_member (JOIN_TRANSITION).
#     """
#     chat_id = event.chat.id
#     # Пришёл один user
#     user = event.new_chat_member.user
#     reason = "chat_member: JOIN_TRANSITION"

#     # Оборачиваем в список, чтобы переиспользовать handle_new_members
#     await handle_new_members(
#         bot=event.bot,
#         chat_id=chat_id,
#         new_members=[user],
#         reason=reason
#     )
        
    
# @manager_router.chat_member(ChatMemberUpdatedFilter(member_status_changed=LEAVE_TRANSITION))
# async def member_left_chat_member(event: ChatMemberUpdated):
#     """
#     Новый формат ухода: chat_member (LEAVE_TRANSITION).
#     """
#     chat_id = event.chat.id
#     user = event.new_chat_member.user
#     reason = "chat_member: LEAVE_TRANSITION"
#     await handle_member_left(event.bot, chat_id, user, reason)
    
    


@manager_router.message(F.text)
async def handle_group_text_message(message: Message):
    """
    Обработка текстовых сообщений в группе:
    - Проверка пользователя в Sheets
    - Сохранение в Sheets
    - Проверка на спам (OpenAI)
    """
    chat_id = message.chat.id
    user_id = message.from_user.id
    username = message.from_user.username or ""
    first_name = message.from_user.first_name or ""
    last_name = message.from_user.last_name or ""
    full_name = f"{first_name} {last_name}".strip()

    date_ts = int(message.date.timestamp())
    reply_to = message.reply_to_message.message_id if message.reply_to_message else 0

    # 1) Если пользователя нет в Sheets — добавляем
    if not user_exists(user_id):
        add_user_row(user_id, username, full_name, chat_id)

    # 2) Сохраняем сообщение (spam='No' по умолчанию)
    add_message_row(
        message_id=message.message_id,
        user_id=user_id,
        text=message.text,
        date_ts=date_ts,
        reply_to=reply_to,
        chat_id=chat_id,
        msg_type="text",
        spam_flag="No"
    )

    # 3) Проверка на спам (если нужно). Предполагаем is_spam — асинхронная
    #    Если нет — уберите await
    if (await is_spam(message.text)):
        # 3.1) Пересылаем админу (MANAGER_CHAT_ID)
        try:
            await message.bot.forward_message(
                chat_id=config.MANAGER_CHAT_ID,
                from_chat_id=chat_id,
                message_id=message.message_id
            )
        except TelegramBadRequest as e:
            logging.error(f"Ошибка пересылки админу: {e}")

        # 3.2) Удаляем из чата
        try:
            await message.bot.delete_message(chat_id, message.message_id)
        except TelegramBadRequest as e:
            logging.error(f"Ошибка удаления спам-сообщения: {e}")

        # 3.3) Помечаем как спам в Sheets
        mark_message_as_spam(message.message_id)

        # 3.4) Уведомляем менеджера
        display_name = f"@{username}" if username else full_name
        note = f"Удалено СПАМ-сообщение от {display_name} (ID: {user_id})."
        await notify_manager(message.bot, note)

    # Пример: если хотите удалить сообщение через schedule:
    # schedule_message_for_deletion(chat_id, message.message_id, delay=120)
    # (Удалится через 2 минуты, когда сработает schedule.run_pending())
