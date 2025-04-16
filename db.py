import os
from datetime import datetime
from typing import Optional, Dict, Any, List
import json

# SQLAlchemy imports
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.ext.asyncio import AsyncEngine
from sqlalchemy.ext.asyncio import AsyncConnection
from sqlalchemy import text

# ------------------------------------------------------------------------
# 1) Create the async Engine (similar to your dbConnect in PHP)
# ------------------------------------------------------------------------

# You would load these from a config file or environment, just like in PHP.
# For example, if the original config_010.php had:
#   $DB_HOST, $DB_NAME, $DB_USER, $DB_PASS
# you could place them in environment variables or read from a .env, etc.
DB_HOST = os.getenv('DB_HOST', '127.0.0.1')
DB_NAME = os.getenv('DB_NAME', 'mydb')
DB_USER = os.getenv('DB_USER', 'user')
DB_PASS = os.getenv('DB_PASS', 'password')

# Here, we create the async engine. Example with MySQL + aiomysql:
DATABASE_URL = f"mysql+aiomysql://{DB_USER}:{DB_PASS}@{DB_HOST}/{DB_NAME}?charset=utf8mb4"

engine: AsyncEngine = create_async_engine(
    DATABASE_URL,
    echo=False,  # or True for debug
    future=True
)


# ------------------------------------------------------------------------
# 2) USERS block
# ------------------------------------------------------------------------
async def get_user_by_telegram_id(telegram_id: int) -> Optional[Dict[str, Any]]:
    """
    SELECT * FROM users WHERE telegram_id = :tg LIMIT 1
    Return a dict of fields if found, else None
    """
    query = text("""
        SELECT * 
          FROM users 
         WHERE telegram_id = :tg
         LIMIT 1
    """)
    async with engine.connect() as conn:
        result = await conn.execute(query, {"tg": telegram_id})
        row = result.fetchone()
        if row is None:
            return None
        # row is a SQLAlchemy Row; convert to dict
        return dict(row._mapping)


async def create_user(telegram_id: int, username: str) -> int:
    """
    Create a 'demo' user, returning its auto-increment ID.
    Demo = 30 days, 20 requests, subscription_tier='demo'
    """
    demo_expire = (datetime.now() 
                   +  # offset of 30 days
                   # you can use timedelta(days=30)
                   # if you prefer a simpler approach
                   # but let's just show a manual way:
                   # from datetime import timedelta
                   # + timedelta(days=30)
                   # 
                   # For clarity, let's do it in code:
                   # (datetime.now() + timedelta(days=30)).strftime(...)
                   # We'll store in DB as string or let DB handle timestamp
                   # For MySQL, a DATETIME field is typical
                   # We'll pass a string to the param:
                   None
                  ) 

    # In practice, you should do:
    from datetime import timedelta
    expire_datetime = datetime.now() + timedelta(days=30)
    demo_expire_str = expire_datetime.strftime('%Y-%m-%d %H:%M:%S')
    demo_requests = 20

    query = text("""
        INSERT INTO users (
          telegram_id,
          username,
          subscription_tier,
          demo_expire_at,
          demo_requests_left,
          created_at
        ) VALUES (
          :tg,
          :uname,
          'demo',
          :demoExp,
          :demoLeft,
          NOW()
        )
    """)

    async with engine.begin() as conn:  # begin transaction
        result = await conn.execute(
            query,
            {
                "tg": telegram_id,
                "uname": username,
                "demoExp": demo_expire_str,
                "demoLeft": demo_requests
            }
        )
        # with SQLAlchemy Core+MySQL, last inserted ID is in result.lastrowid
        last_id = result.lastrowid
    return last_id


def is_demo_expired(user: Dict[str, Any]) -> bool:
    """
    Check if current date > user['demo_expire_at'].
    This can be synchronous logic (no DB calls needed).
    """
    demo_expire_at = user.get('demo_expire_at')
    if not demo_expire_at:
        return False
    expire_time = datetime.strptime(demo_expire_at, '%Y-%m-%d %H:%M:%S')
    return datetime.now() > expire_time


async def decrement_demo_requests(telegram_id: int) -> None:
    """
    UPDATE users SET demo_requests_left = demo_requests_left - 1
    WHERE telegram_id = :tg
    """
    query = text("""
        UPDATE users
           SET demo_requests_left = demo_requests_left - 1
         WHERE telegram_id = :tg
    """)
    async with engine.begin() as conn:
        await conn.execute(query, {"tg": telegram_id})


def is_subscription_expired(user: Dict[str, Any]) -> bool:
    """
    If user has subscription_expire_at, check if now > subscription_expire_at
    If no subscription_expire_at, consider expired (True).
    """
    sub_exp = user.get('subscription_expire_at')
    if not sub_exp:
        return True
    expire_time = datetime.strptime(sub_exp, '%Y-%m-%d %H:%M:%S')
    return datetime.now() > expire_time


async def check_and_reset_daily_limit(user: Dict[str, Any]) -> Dict[str, Any]:
    """
    If date changed, daily_used = 0, daily_reset_date = today
    Return updated user dict (the caller can stash it).
    """
    now_day_str = datetime.now().strftime('%Y-%m-%d')
    user_day_str = "2000-01-01"
    if user.get('daily_reset_date'):
        user_day_str = user['daily_reset_date'][:10]

    if now_day_str > user_day_str:
        query = text("""
            UPDATE users
               SET daily_used = 0,
                   daily_reset_date = :today
             WHERE id = :id
        """)
        async with engine.begin() as conn:
            await conn.execute(query, {"today": now_day_str, "id": user['id']})
        # Reflect changes in the local dict:
        user['daily_used'] = 0
        user['daily_reset_date'] = now_day_str
    return user


async def increment_daily_used(user: Dict[str, Any]) -> None:
    """
    daily_used = daily_used + 1
    """
    query = text("""
        UPDATE users
           SET daily_used = daily_used + 1
         WHERE id = :id
    """)
    async with engine.begin() as conn:
        await conn.execute(query, {"id": user['id']})


async def get_user_state(user_id: int) -> str:
    """
    SELECT state FROM users WHERE id = :id
    If not found, return 'idle'
    """
    query = text("""SELECT state FROM users WHERE id=:id LIMIT 1""")
    async with engine.connect() as conn:
        result = await conn.execute(query, {"id": user_id})
        row = result.fetchone()
        if row is None or row[0] is None:
            return "idle"
        return row[0]


async def set_user_state(user_id: int, new_state: str) -> None:
    """
    UPDATE users SET state = :st WHERE id = :id
    """
    query = text("""
        UPDATE users
           SET state = :st
         WHERE id = :id
    """)
    async with engine.begin() as conn:
        await conn.execute(query, {"st": new_state, "id": user_id})


# ------------------------------------------------------------------------
# 3) DOC_CHUNKS block
# ------------------------------------------------------------------------
async def insert_doc_chunk(chunk_text: str, embedding_json: str) -> int:
    """
    INSERT INTO doc_chunks (chunk_text, embedding)
    VALUES (:chunk, :emb)
    Return the inserted row ID
    """
    query = text("""
        INSERT INTO doc_chunks (chunk_text, embedding)
        VALUES (:chunk, :emb)
    """)
    async with engine.begin() as conn:
        result = await conn.execute(query, {"chunk": chunk_text, "emb": embedding_json})
        inserted_id = result.lastrowid
    return inserted_id


async def get_all_doc_chunks() -> List[Dict[str, Any]]:
    """
    SELECT id, chunk_text, embedding FROM doc_chunks ORDER BY id ASC
    Return list of dicts
    """
    query = text("""
        SELECT id, chunk_text, embedding
          FROM doc_chunks
         ORDER BY id ASC
    """)
    async with engine.connect() as conn:
        result = await conn.execute(query)
        rows = result.fetchall()
        return [dict(r._mapping) for r in rows]


# ------------------------------------------------------------------------
# 4) CHAT_HISTORY block
# ------------------------------------------------------------------------
async def save_chat_message(
    user_id: int,
    role: str,
    content: str,
    message_type: str = 'text',
    file_path: Optional[str] = None
) -> int:
    """
    INSERT INTO chat_history (user_id, role, content, message_type, file_path)
    VALUES (:uid, :rl, :ct, :mt, :fp)
    Return inserted row ID
    """
    query = text("""
        INSERT INTO chat_history (user_id, role, content, message_type, file_path)
        VALUES (:uid, :rl, :ct, :mt, :fp)
    """)
    async with engine.begin() as conn:
        result = await conn.execute(
            query,
            {
                "uid": user_id,
                "rl": role,
                "ct": content,
                "mt": message_type,
                "fp": file_path
            }
        )
        inserted_id = result.lastrowid
    return inserted_id


async def get_last_messages(user_id: int, limit: int = 10) -> List[Dict[str, Any]]:
    """
    SELECT * FROM chat_history
    WHERE user_id = :uid
    ORDER BY id DESC
    LIMIT :lim
    Return them in chronological order (reverse of SELECT).
    """
    query = text("""
        SELECT * 
          FROM chat_history
         WHERE user_id = :uid
         ORDER BY id DESC
         LIMIT :lim
    """)
    async with engine.connect() as conn:
        # For MySQL, we can pass limit as an int param. For some backends,
        # might need to embed it in text carefully.
        result = await conn.execute(
            query.bindparams(uid=user_id, lim=limit)
        )
        rows = result.fetchall()

    reversed_rows = list(reversed(rows))
    return [dict(r._mapping) for r in reversed_rows]


async def get_all_messages_count(user_id: int) -> int:
    """
    SELECT COUNT(*) as cnt FROM chat_history WHERE user_id = :uid
    """
    query = text("""
        SELECT COUNT(*) AS cnt
          FROM chat_history
         WHERE user_id = :uid
    """)
    async with engine.connect() as conn:
        result = await conn.execute(query, {"uid": user_id})
        row = result.fetchone()
        return int(row['cnt'] if row else 0)


async def get_old_messages_for_summary(user_id: int, count: int = 10) -> List[Dict[str, Any]]:
    """
    SELECT * FROM chat_history
    WHERE user_id = :uid
    ORDER BY id ASC
    LIMIT :c
    """
    query = text("""
        SELECT *
          FROM chat_history
         WHERE user_id = :uid
         ORDER BY id ASC
         LIMIT :c
    """)
    async with engine.connect() as conn:
        result = await conn.execute(query, {"uid": user_id, "c": count})
        rows = result.fetchall()
        return [dict(r._mapping) for r in rows]


async def delete_messages_by_ids(ids: List[int]) -> None:
    """
    DELETE FROM chat_history WHERE id IN (:inlist)
    """
    if not ids:
        return

    # We'll build a dynamic statement
    placeholders = ", ".join(str(x) for x in ids)
    query_text = f"DELETE FROM chat_history WHERE id IN ({placeholders})"
    async with engine.begin() as conn:
        await conn.execute(text(query_text))


async def compress_old_messages(user_id: int) -> None:
    """
    Example "summary" approach: If total msg count > 20, 
    get first 10, summarize them, then delete those 10, then
    save the summary as one message.
    """
    total_count = await get_all_messages_count(user_id)
    if total_count <= 20:
        return

    old_msgs = await get_old_messages_for_summary(user_id, 10)
    if len(old_msgs) < 10:
        return

    # create summary
    summary = f"(Summary of {total_count} messages...)"  # or call GPT to do it for real

    msg_ids = [m['id'] for m in old_msgs]
    # Delete old ones
    await delete_messages_by_ids(msg_ids)

    # Insert the summary as a single chat message
    await save_chat_message(user_id, 'assistant', summary, 'text', None)
