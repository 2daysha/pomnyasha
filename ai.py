import os
import requests
from dotenv import load_dotenv

load_dotenv()

def ask_gigachat(prompt: str) -> str:
    if not prompt.strip():
        return "Пустое сообщение"
    client_id = os.getenv("GIGACHAT_CLIENT_ID")
    client_secret = os.getenv("GIGACHAT_CLIENT_SECRET")
    scope = os.getenv("GIGACHAT_AUTH_SCOPE", "GIGACHAT_API_PERS")
    api_url = os.getenv("GIGACHAT_API", "https://gigachat.devices.sberbank.ru/api/v1/chat/completions")

    token_resp = requests.post(
        "https://ngw.devices.sberbank.ru:9443/api/v2/oauth",
        headers={
            "Authorization": "Basic " + requests.auth._basic_auth_str(client_id, client_secret),
            "RqUID": "pomnyasha-token",
            "Content-Type": "application/x-www-form-urlencoded"
        },
        data={"scope": scope},
        verify=False,
    )

    if token_resp.status_code != 200:
        return "Ошибка авторизации GigaChat"
    token = token_resp.json().get("access_token")
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    payload = {
        "model": "GigaChat",
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.7
    }

    r = requests.post(api_url, headers=headers, json=payload, verify=False)
    if r.status_code != 200:
        return "Ошибка при обращении к GigaChat"
    try:
        return r.json()["choices"][0]["message"]["content"]
    except Exception:
        return "Ошибка обработки ответа GigaChat"