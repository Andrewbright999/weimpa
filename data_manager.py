from db import (
    getUserByTelegramId,
    createUser,
    saveChatMessage,
    getLastMessages
)



async def check_and_add_user(chat_id, username):
    # user  = getUserByTelegramId(chat_id)
    # if not user:
    #     createUser(chat_id, username)
    #     user = getUserByTelegramId(chat_id)
    # return user["id"]
    return "113231"