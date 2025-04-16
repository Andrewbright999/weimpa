import os
import asyncio
from datetime import datetime
from typing import Optional, List, Dict, Any

import openai
from openai import AsyncOpenAI

from config import config

# =============================================================================
# Инициализация клиентов для GPT, Embeddings, Whisper
# (из вашего кода)
# =============================================================================
client_gpt = AsyncOpenAI(api_key=config.OPENAI_GPT_KEY)
client_embed = AsyncOpenAI(api_key=config.OPENAI_EMBEDDING_KEY)
client_whisper = AsyncOpenAI(api_key=config.OPENAI_WHISPER_KEY)

# =============================================================================
# Пример системного промпта (weimpaSystemPrompt) + заглушки с compress/get_last
# =============================================================================
weimpaSystemPrompt = """Ты — чат-бот сообщества «United Triathlon».
Используешь данные из этого расписания и инструкций и RAG. Если чего-то нет, отправляй к менеджеру @unitedbytriathlon
...
"""

async def compress_old_messages(user_id: str) -> None:
    # Заглушка — сжимает/архивирует сообщения
    pass

async def get_last_messages(user_id: str, limit: int = 15) -> List[Dict[str, str]]:
    # Заглушка — возвращает последние сообщения
    return [
        {"role": "user", "content": "Привет, когда ближайшая пробежка?"},
        {"role": "assistant", "content": "Привет! Ближайшая пробежка во вторник вечером..."},
    ][:limit]


# =============================================================================
# 1. get_gpt_chat_with_history (аналог вашего PHP getGPTChatWithHistory)
# =============================================================================

async def get_gpt_chat_with_history(
    user_id: str,
    limit: int = 15,
    extra_system: Optional[str] = None
) -> str:
    try:
        await compress_old_messages(user_id)
        rows = await get_last_messages(user_id, limit)

        now = datetime.now()
        en_day = now.strftime("%A")
        days_ru = {
            "Monday": "Понедельник",
            "Tuesday": "Вторник",
            "Wednesday": "Среда",
            "Thursday": "Четверг",
            "Friday": "Пятница",
            "Saturday": "Суббота",
            "Sunday": "Воскресенье"
        }
        ru_day = days_ru.get(en_day, en_day)
        date_str = now.strftime("%d.%m.%Y %H:%M")
        date_note = f"Сейчас (Dubai): {ru_day}, {date_str}"

        system_content = f"{weimpaSystemPrompt}\n\n{date_note}"
        if extra_system:
            system_content += f"\n\n(Доп. контекст)\n{extra_system}"

        messages = [{"role": "system", "content": system_content}]
        for r in rows:
            role = r.get("role", "user")
            content = r.get("content", "")
            if role not in ["assistant", "user", "system"]:
                role = "user"
            if not content.strip():
                content = " "
            messages.append({"role": role, "content": content})

        completion = await client_gpt.chat.completions.create(
            model="gpt-4o",
            messages=messages,
            temperature=0.7
        )

        if completion.choices and completion.choices[0].message:
            return completion.choices[0].message.content

        return f"Не удалось получить ответ: {completion.to_dict()}"
    except openai.APIConnectionError as e:
        return f"Ошибка подключения к API: {e}"
    except openai.APIStatusError as e:
        return (
            f"API вернул ошибку (статус {e.status_code}). "
            f"ID запроса: {e.request_id}. "
            f"Текст: {e.message}"
        )
    except openai.APIError as e:
        return f"Общая ошибка API: {e}"
    except Exception as e:
        return f"Непредвиденная ошибка: {e}"


# =============================================================================
# 2. get_embedding (аналог вашего PHP getEmbedding)
# =============================================================================

async def get_embedding(text: str) -> Optional[List[float]]:
    try:
        response = await client_embed.embeddings.create(
            model="text-embedding-ada-002",
            input=text
        )
        if response.data and len(response.data) > 0:
            return response.data[0].embedding
        return None
    except openai.APIError as e:
        print(f"Ошибка при получении эмбеддинга: {e}")
        return None
    except Exception as e:
        print(f"Непредвиденная ошибка: {e}")
        return None


# =============================================================================
# 3. send_to_whisper (аналог вашего PHP sendToWhisper)
# =============================================================================

async def send_to_whisper(local_ogg_path: str) -> Dict[str, Any]:
    try:
        with open(local_ogg_path, "rb") as audio_file:
            response = await client_whisper.audio.transcriptions.create(
                file=audio_file,
                model="whisper-1"
            )

        if hasattr(response, "text"):
            return {"text": response.text}
        else:
            return {"error": f"Неизвестный формат ответа: {response.to_dict()}"}

    except openai.APIConnectionError as e:
        return {"error": f"Ошибка подключения: {e}"}
    except openai.APIStatusError as e:
        return {
            "error": (
                f"API вернул ошибку (статус {e.status_code}). "
                f"ID запроса: {e.request_id}. Текст: {e.message}"
            )
        }
    except openai.APIError as e:
        return {"error": f"Общая ошибка API: {e}"}
    except Exception as e:
        return {"error": f"Непредвиденная ошибка: {e}"}


# =============================================================================
# 4. Новая функция is_spam (аналог PHP isSpam)
# =============================================================================

async def is_spam(text: str) -> bool:
    """
    Делает запрос к GPT (gpt-4) с жёсткими инструкциями:
    Вернуть ровно "SPAM" или "NOT_SPAM".
    Если SPAM — возвращаем True, иначе False.
    Если есть ошибка — подстраховка: считаем, что NOT_SPAM (False).
    """
    # Защитимся от слишком длинных сообщений
    if len(text) > 2000:
        text = text[:2000]

    system_prompt = (
        "Ты - помощник по модерации в чате сообщества триатлонистов. "
        "Я дам тебе сообщение. Твоя задача: определить, является ли оно спамом "
        "или рекламой, не связанной с темой триатлона/спорта, "
        "или это обычная переписка. "
        "Если это спам - ответь строго \"SPAM\" "
        "Если это не спам - ответь строго \"NOT_SPAM\" "
        "Без пояснений, только одно слово. "
        "Ссылка на Google Maps или другой сервис картографии или "
        "видеохостинг, такой как YouTube, — это не спам."
    )

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": text},
    ]

    try:
        response = await client_gpt.chat.completions.create(
            model="gpt-4",
            messages=messages,
            temperature=0.0,
            max_tokens=10
        )

        raw_answer = ""
        if response.choices and response.choices[0].message:
            raw_answer = response.choices[0].message.content.strip().upper()

        # Для отладки
        print(f"DEBUG (is_spam): GPT returned: {raw_answer}")

        return (raw_answer == "SPAM")

    except openai.APIError as e:
        # При ошибке считаем, что NOT_SPAM, чтобы не заблокировать
        print(f"ERROR in is_spam: {e}")
        return False
    except Exception as e:
        print(f"Unexpected error in is_spam: {e}")
        return False


# =============================================================================
# 5. Новая функция is_insult (аналог PHP isInsult)
# =============================================================================

async def is_insult(text: str) -> bool:
    """
    Делает запрос к GPT (gpt-4) с жёсткими инструкциями:
    Вернуть ровно "INSULT" или "NOT_INSULT".
    Если INSULT — возвращаем True, иначе False.
    При ошибках возвращаем False.
    """
    if len(text) > 2000:
        text = text[:2000]

    system_prompt = (
        "Ты - помощник по модерации в чате сообщества триатлонистов. "
        "Я дам тебе сообщение. Твоя задача: определить, содержит ли оно "
        "оскорбления или неуместную агрессию. "
        "Если да, ответь строго \"INSULT\". "
        "Если нет, ответь строго \"NOT_INSULT\". "
        "Без пояснений, только одно слово."
    )

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user",   "content": text},
    ]

    try:
        response = await client_gpt.chat.completions.create(
            model="gpt-4",
            messages=messages,
            temperature=0.0,
            max_tokens=10
        )

        raw_answer = ""
        if response.choices and response.choices[0].message:
            raw_answer = response.choices[0].message.content.strip().upper()

        # Для отладки
        print(f"DEBUG (is_insult): GPT returned: {raw_answer}")

        return (raw_answer == "INSULT")

    except openai.APIError as e:
        print(f"ERROR in is_insult: {e}")
        return False
    except Exception as e:
        print(f"Unexpected error in is_insult: {e}")
        return False


# =============================================================================
# Пример использования
# =============================================================================

async def main_example():
    print("=== Пример GPT ===")
    gpt_answer = await get_gpt_chat_with_history(
        user_id="user123",
        limit=2,
        extra_system="(Тестовое дополнение к system-промпту)"
    )
    print("GPT-ответ:", gpt_answer, "\n")

    print("=== Пример Embedding ===")
    emb = await get_embedding("Пример текста для эмбеддингов")
    if emb:
        print(f"Векторная длина эмбеддинга: {len(emb)}")
    else:
        print("Не удалось получить эмбеддинг")

    print("\n=== Пример Whisper ===")
    whisper_result = await send_to_whisper("voice.ogg")
    print("Результат Whisper:", whisper_result)

    print("\n=== Пример is_spam ===")
    spam_test = await is_spam("Купите тренажёр для накачки пресса!")
    print("Это спам?", spam_test)

    print("\n=== Пример is_insult ===")
    insult_test = await is_insult("Ты вообще не понимаешь ничего!")
    print("Это оскорбление?", insult_test)


if __name__ == "__main__":
    asyncio.run(main_example())
