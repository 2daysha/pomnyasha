import os
import requests
import uuid
from dotenv import load_dotenv

load_dotenv()

AUTHORIZATION_KEY = os.getenv("GIGACHAT_AUTHORIZATION_KEY")
ACCESS_URL = "https://ngw.devices.sberbank.ru:9443/api/v2/oauth"
API_URL = "https://gigachat.devices.sberbank.ru/api/v1/chat/completions"

TOKEN_CACHE = None


def get_token():
    global TOKEN_CACHE
    if TOKEN_CACHE:
        return TOKEN_CACHE

    try:
        rquid = str(uuid.uuid4())
        r = requests.post(
            ACCESS_URL,
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "Accept": "application/json",
                "RqUID": rquid,
                "Authorization": f"Bearer {AUTHORIZATION_KEY}"
            },
            data={"scope": "GIGACHAT_API_PERS"},
            verify=False
        )

        if r.status_code != 200:
            return None

        TOKEN_CACHE = r.json().get("access_token")
        return TOKEN_CACHE
    except:
        return None


def ask_gigachat(message: str) -> str:
    token = get_token()
    if not token:
        return "Ошибка авторизации GigaChat"

    try:
        r = requests.post(
            API_URL,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
            json={
                "model": "GigaChat",
                "messages": [
                    {"role": "system", "content": "Ты — Помняша, ИИ помощник-планировщик."},
                    {"role": "user", "content": message}
                ],
                "temperature": 0.7,
                "max_tokens": 500
            },
            verify=False,
            timeout=20
        )

        if r.status_code != 200:
            TOKEN_CACHE = None
            return "Ошибка API GigaChat"

        return r.json()["choices"][0]["message"]["content"]

    except Exception:
        return "Ошибка соединения с GigaChat"