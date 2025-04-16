import os
import json
import logging
import asyncio
import aioschedule as schedule

from aiogram import Dispatcher, exceptions
from aiogram.client.bot import Bot
from aiogram.client.default import DefaultBotProperties

from config import config
from manager_router import manager_router
from communicator_router import communicator_router


# Настраиваем логирование в файл bot.log + в консоль
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
    handlers=[
        logging.FileHandler("bot.log", encoding="utf-8"),
        logging.StreamHandler()
    ]
)


# Инициализируем бота-«Коммуникатор»
communicator_bot = Bot(
    token=(config.BOT_TOKEN_1).replace(" ", ""),
    default=DefaultBotProperties(parse_mode=config.PARSE_MODE)
)
communicator_dp = Dispatcher()


# Инициализируем бота-«Менеджер»
manager_bot = Bot(
    token=(config.BOT_TOKEN_2).replace(" ", ""),
    default=DefaultBotProperties(parse_mode=config.PARSE_MODE)
)
manager_dp = Dispatcher()


async def remove_welcome_message():
    """
    Периодическая задача: удаляет приветственное сообщение (если есть).
    """
    if not os.path.exists(config.CURRENT_WELCOME_FILE):
        return

    try:
        with open(config.CURRENT_WELCOME_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        logging.error(f"Не смогли прочитать {config.CURRENT_WELCOME_FILE}: {e}")
        return

    if not isinstance(data, dict):
        return

    chat_id = data.get("chat_id")
    message_id = data.get("message_id")
    if not chat_id or not message_id:
        return

    # Удаляем
    try:
        await manager_bot.delete_message(chat_id, message_id)
        logging.info(f"Удалили приветственное сообщение (msg_id={message_id}) в чате {chat_id}")
    except exceptions.TelegramBadRequest as e:
        logging.error(f"Ошибка удаления приветствия: {e}")

    # Обнуляем файл
    try:
        with open(config.CURRENT_WELCOME_FILE, "w", encoding="utf-8") as f:
            f.write("")
    except Exception as e:
        logging.error(f"Ошибка при очистке файла {config.CURRENT_WELCOME_FILE}: {e}")


async def schedule_runner():
    """
    Запускаем планировщик aioschedule в отдельном корутине.
    Каждую секунду проверяем задания.
    """
    while True:
        await schedule.run_pending()
        await asyncio.sleep(1)


async def main():
    # Подключаем роутеры
    communicator_dp.include_router(communicator_router)
    manager_dp.include_router(manager_router)

    # Планировщик: каждые 5 минут удаляем приветственное сообщение
    schedule.every(5).minutes.do(remove_welcome_message)

    # Параллельно запускаем:
    # 1) Поллинг бота-«Менеджера» (+ chat_member)
    # 2) Поллинг бота-«Коммуникатора» (только message)
    # 3) Планировщик (schedule)
    await asyncio.gather(
        manager_dp.start_polling(
            manager_bot,
            allowed_updates=["message", "chat_member"]
        ),
        communicator_dp.start_polling(
            communicator_bot,
            allowed_updates=["message"]
        ),
        schedule_runner()
    )


if __name__ == "__main__":
    asyncio.run(main())
