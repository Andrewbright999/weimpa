import json
import logging
import datetime
from typing import Optional

from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# Предположим, что config.py содержит две переменные:
# SERVICE_ACCOUNT_JSON (string) и config.GOOGLE_SHEET_ID (string).
# Или получите их из окружения/env, как вам удобнее.
from config import config


def get_sheets_service():
    """
    Создаёт Google Sheets service на основе SERVICE_ACCOUNT_JSON.
    """
    logging.debug("DEBUG: Enter getSheetsService()")

    try:
        creds_array = config.SERVICE_ACCOUNT_JSON  # Уже dict, не нужно json.loads
    except Exception as e:
        logging.error("FATAL: SERVICE_ACCOUNT_JSON missing or invalid: %s", e)
        return None

    try:
        creds = Credentials.from_service_account_info(
            creds_array,
            scopes=["https://www.googleapis.com/auth/spreadsheets"]
        )
    except Exception as e:
        logging.error("FATAL: Can't create credentials from service account info: %s", e)
        return None

    try:
        service = build("sheets", "v4", credentials=creds)
        logging.debug("DEBUG: getSheetsService() - created new Sheets service")
        return service
    except Exception as e:
        logging.error("FATAL: Error building Sheets service: %s", e)
        return None



def user_exists(user_id: str) -> bool:
    """
    Аналог PHP: userExists($userId).
    Проверяем, есть ли пользователь (userId) в листе "Users" (колонка A).
    """
    logging.debug("DEBUG: userExists(%s) called", user_id)
    service = get_sheets_service()
    if not service:
        logging.error("ERROR: Sheets service is null, aborting userExists check.")
        return False

    range_name = "Users!A:A"  # Колонка A в листе Users
    print(config.GOOGLE_SHEET_ID)
    try:
        response = service.spreadsheets().values().get(
            spreadsheetId=config.GOOGLE_SHEET_ID,
            range=range_name
        ).execute()
        values = response.get("values", [])

        if not values:
            logging.debug("DEBUG: userExists => 'Users' is empty, returning false")
            return False

        for row_index, row in enumerate(values):
            if row_index == 0:
                # Предположим, что в A1 написано "user_id"
                continue
            if len(row) > 0 and str(row[0]) == str(user_id):
                logging.debug("DEBUG: userExists => found userId=%s at row %d", user_id, row_index)
                return True

        logging.debug("DEBUG: userExists => not found userId=%s", user_id)
        return False
    except HttpError as e:
        logging.error("EXCEPTION in userExists: %s", e)
        return False


def add_user_row(user_id: str, username: str, full_name: str, chat_id: str):
    """
    Аналог PHP: addUserRow($userId, $username, $fullName, $chatId).
    Добавляет строку в лист "Users".
    """
    logging.debug("DEBUG: addUserRow(): userId=%s, user=%s, fullName=%s, chatId=%s",
                  user_id, username, full_name, chat_id)

    service = get_sheets_service()
    if not service:
        logging.error("ERROR: Sheets service is null, aborting addUserRow.")
        return

    now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    values = [[
        user_id,
        username,
        full_name,
        now_str,
        chat_id
    ]]

    body = {
        "values": values
    }
    params = {"valueInputOption": "RAW"}
    range_name = "Users"

    logging.debug("DEBUG: addUserRow => about to append to 'Users'")
    try:
        result = service.spreadsheets().values().append(
            spreadsheetId=config.GOOGLE_SHEET_ID,
            range=range_name,
            valueInputOption="RAW",
            body=body
        ).execute()
        logging.debug("DEBUG: addUserRow => append result=%s", result.get("updates"))
    except HttpError as e:
        logging.error("EXCEPTION in addUserRow: %s", e)

    logging.debug("DEBUG: addUserRow() finished.")


def add_message_row(
    message_id: str,
    user_id: str,
    text: str,
    date_ts: int,
    reply_to: str,
    chat_id: str,
    msg_type: str = "text",
    spam_flag: str = "No"
):
    """
    Аналог PHP: addMessageRow().
    Добавляем строку в лист "Messages" (8 колонок).
    Последняя колонка — Spam (Yes/No).
    """
    logging.debug("DEBUG: addMessageRow() called. messageId=%s, userId=%s, text=%s, date=%s, replyTo=%s, chatId=%s, type=%s, spam=%s",
                  message_id, user_id, text, date_ts, reply_to, chat_id, msg_type, spam_flag)

    service = get_sheets_service()
    if not service:
        logging.error("ERROR: Sheets service is null, aborting addMessageRow.")
        return

    # Преобразуем UNIX timestamp в строку
    date_str = datetime.datetime.fromtimestamp(date_ts).strftime("%Y-%m-%d %H:%M:%S")

    values = [[
        message_id,
        user_id,
        text,
        date_str,
        reply_to,
        chat_id,
        msg_type,
        spam_flag
    ]]

    body = {"values": values}
    range_name = "Messages"

    logging.debug("DEBUG: addMessageRow => about to append to 'Messages'")
    try:
        result = service.spreadsheets().values().append(
            spreadsheetId=config.GOOGLE_SHEET_ID,
            range=range_name,
            valueInputOption="RAW",
            body=body
        ).execute()
        logging.debug("DEBUG: addMessageRow => append result=%s", result.get("updates"))
    except HttpError as e:
        logging.error("EXCEPTION in addMessageRow: %s", e)

    logging.debug("DEBUG: addMessageRow() finished.")


def mark_message_as_spam(message_id: str):
    """
    Аналог PHP: markMessageAsSpam($messageId).
    Ищем messageId в колонке A листа "Messages", 
    и ставим "Yes" в колонку H (8-я колонка).
    """
    logging.debug("DEBUG: markMessageAsSpam(%s) called.", message_id)

    service = get_sheets_service()
    if not service:
        logging.error("ERROR: Sheets service is null, aborting markMessageAsSpam.")
        return

    range_name = "Messages!A:A"
    try:
        response = service.spreadsheets().values().get(
            spreadsheetId=config.GOOGLE_SHEET_ID,
            range=range_name
        ).execute()
        values = response.get("values", [])

        if not values:
            logging.debug("DEBUG: markMessageAsSpam => 'Messages' is empty, nothing to update")
            return

        for row_index, row in enumerate(values):
            if row_index == 0:
                # заголовок колонок
                continue

            current_id = row[0] if len(row) > 0 else None
            if str(current_id) == str(message_id):
                # Нашли нужную строку
                real_row_number = row_index + 1  # row_index 0-based => Sheets 1-based
                update_range = f"Messages!H{real_row_number}:H{real_row_number}"

                body = {"values": [["Yes"]]}
                result = service.spreadsheets().values().update(
                    spreadsheetId=config.GOOGLE_SHEET_ID,
                    range=update_range,
                    valueInputOption="RAW",
                    body=body
                ).execute()

                logging.debug("DEBUG: markMessageAsSpam => updated row %d => Spam=Yes", real_row_number)
                return  # Достаточно обновить первую найденную строку

        logging.debug("DEBUG: markMessageAsSpam => messageId=%s not found in 'Messages'", message_id)
    except HttpError as e:
        logging.error("EXCEPTION in markMessageAsSpam: %s", e)
