# SPDX-License-Identifier: GPL-3.0-or-later
import base64
import html
import json
import os
import re
import time

import openai
import requests
from bs4 import BeautifulSoup

# =====================================================================================
# Configuration
# =====================================================================================
USERNAME = os.getenv('EUSERV_USERNAME', '改为你的EUserV客户ID 或 邮箱')
PASSWORD = os.getenv('EUSERV_PASSWORD', '改为你的EUserV的密码')
MAILPARSER_DOWNLOAD_URL_ID = os.getenv('MAILPARSER_DOWNLOAD_URL_ID', '改为你的Mailparser下载URL的最后几位')

OPENAI_API_KEY = os.getenv('OPENAI_API_KEY', 'sk-xxxxxxxxxxxxxxxxxxx')
OPENAI_API_BASE_URL = os.getenv('OPENAI_API_BASE_URL', 'https://api.openai.com/v1')
OPENAI_MODEL_NAME = os.getenv('OPENAI_MODEL_NAME', 'gpt-4o')

MAILPARSER_DOWNLOAD_BASE_URL = "https://files.mailparser.io/d/"
TG_BOT_TOKEN = os.getenv('TG_BOT_TOKEN', "改为你的Telegram机器人Token")
TG_USER_ID = os.getenv('TG_USER_ID', "改为你的用户ID")
TG_API_HOST = os.getenv('TG_API_HOST', "https://api.telegram.org")

proxy_url = os.getenv('PROXY_URL')
PROXIES = {"http": proxy_url, "https": proxy_url} if proxy_url else None

# =====================================================================================
# Global Settings
# =====================================================================================
LOGIN_MAX_RETRY_COUNT = 5
USER_AGENT = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/95.0.4638.69 Safari/537.36")
desp = ""

# =====================================================================================
# Helper Functions
# =====================================================================================
def log(info: str):
    """Formats and prints log messages with corresponding emojis."""
    emoji_map = {
        "正在续费": "🔄", "检测到": "🔍", "ServerID": "🔗", "无需更新": "✅",
        "续订错误": "⚠️", "已成功续订": "🎉", "所有工作完成": "🏁", "登陆失败": "❗",
        "验证通过": "✔️", "验证失败": "❌", "API 使用次数": "📊", "验证码是": "🔢",
        "登录尝试": "🔑", "[MailParser]": "📧", "[Captcha Solver]": "🧩",
        "[AutoEUServerless]": "🌐"
    }
    for key, emoji in emoji_map.items():
        if key in info:
            info = f"{emoji} {info}"
            break
    print(info)
    global desp
    desp += info + "\n\n"

def login_retry(*args, **kwargs):
    """Decorator to handle login retries."""
    def wrapper(func):
        def inner(username, password):
            ret, ret_session = func(username, password)
            max_retry = kwargs.get("max_retry", 3)
            number = 0
            if ret == "-1":
                while number < max_retry:
                    number += 1
                    if number > 1:
                        log(f"[AutoEUServerless] 登录尝试第 {number} 次")
                    sess_id, session = func(username, password)
                    if sess_id != "-1":
                        return sess_id, session
                    elif number == max_retry:
                        return sess_id, session
            return ret, ret_session
        return inner
    return wrapper

# =====================================================================================
# Core Logic
# =====================================================================================
def captcha_solver(captcha_image_url: str, session: requests.session) -> dict:
    """Solves captcha using a compatible OpenAI vision API."""
    log(f"[Captcha Solver] 正在使用 OpenAI 兼容接口，模型: {OPENAI_MODEL_NAME}")
    if not OPENAI_API_KEY or 'sk-xxx' in OPENAI_API_KEY:
        log("[Captcha Solver] OpenAI API Key 未配置。")
        return {}

    try:
        client = openai.OpenAI(api_key=OPENAI_API_KEY, base_url=OPENAI_API_BASE_URL)
        response = session.get(captcha_image_url, proxies=PROXIES)
        response.raise_for_status()
        base64_image = base64.b64encode(response.content).decode('utf-8')

        prompt = (
            "You are an expert captcha solver. Your task is to return ONLY the "
            "characters or the calculated result. If the image contains 'AB12C', "
            "return 'AB12C'. If it's a math problem like '5 x 3', return ONLY "
            "the final number, '15'. Provide no explanations."
        )

        api_response = client.chat.completions.create(
            model=OPENAI_MODEL_NAME,
            messages=[{
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{base64_image}"}}
                ]
            }],
            max_tokens=50
        )
        result_text = api_response.choices[0].message.content.strip()
        log(f"[Captcha Solver] API 返回原始结果: '{result_text}'")
        if not result_text:
            log("[Captcha Solver] API 返回结果为空。")
            return {}
        return {"result": result_text}

    except Exception as e:
        log(f"[Captcha Solver] 调用 OpenAI 兼容接口时发生严重错误: {e}")
        return {}

def get_pin_with_polling_and_comparison(url_id: str) -> str:
    """Intelligently polls Mailparser for a new PIN, avoiding stale data."""
    max_retries, retry_interval, stale_pin = 12, 5, ""

    log("[MailParser] 首次读取，检查是否存在旧PIN...")
    try:
        response = requests.get(f"{MAILPARSER_DOWNLOAD_BASE_URL}{url_id}", proxies=PROXIES, timeout=10)
        if response.status_code == 200:
            data = response.json()
            if data and isinstance(data, list) and data[0] and data[0].get("pin"):
                stale_pin = data[0]["pin"]
                log(f"[MailParser] 发现已存在的旧PIN: {stale_pin}。")
    except Exception:
        log("[MailParser] 首次读取未发现旧PIN或发生错误。")

    log(f"[MailParser] 开始轮询，等待与 '{stale_pin}' 不同的新PIN...")
    for i in range(max_retries):
        try:
            response = requests.get(f"{MAILPARSER_DOWNLOAD_BASE_URL}{url_id}", proxies=PROXIES, timeout=10)
            response.raise_for_status()
            data = response.json()
            if data and isinstance(data, list) and data[0] and data[0].get("pin"):
                current_pin = data[0]["pin"]
                if current_pin != stale_pin:
                    log(f"🎉 [MailParser] 成功！在第 {i + 1} 次尝试时获取到新PIN: {current_pin}")
                    return current_pin
                else:
                    log(f"[MailParser] 第 {i + 1}/{max_retries} 次：拿到的仍是旧PIN '{stale_pin}'，等待...")
            else:
                log(f"[MailParser] 第 {i + 1}/{max_retries} 次：尚未收到任何PIN，等待...")
        except Exception as e:
            log(f"[MailParser] 第 {i + 1}/{max_retries} 次：获取PIN时出错 ({e})，等待...")
        time.sleep(retry_interval)

    log("❌ [MailParser] 超时！在规定时间内未能获取到新的PIN。")
    return ""

@login_retry(max_retry=LOGIN_MAX_RETRY_COUNT)
def login(username: str, password: str) -> (str, requests.session):
    """Handles the complete login process, including captcha."""
    headers = {"user-agent": USER_AGENT, "origin": "https://www.euserv.com"}
    url, captcha_image_url = "https://support.euserv.com/index.iphp", "https://support.euserv.com/securimage_show.php"
    session = requests.Session()

    sess = session.get(url, headers=headers, proxies=PROXIES)
    sess_ids = re.findall(r"PHPSESSID=(\w{10,100});", str(sess.headers))
    if not sess_ids:
        log("无法获取 PHPSESSID。")
        return "-1", session
    sess_id = sess_ids[0]

    session.get("https://support.euserv.com/pic/logo_small.png", headers=headers, proxies=PROXIES)

    login_data = {"email": username, "password": password, "form_selected_language": "en", "Submit": "Login", "subaction": "login", "sess_id": sess_id}
    f = session.post(url, headers=headers, data=login_data, proxies=PROXIES)
    f.raise_for_status()

    if "Hello" not in f.text and "Confirm or change your customer data here" not in f.text:
        if "To finish the login process please solve the following captcha." not in f.text:
            return "-1", session

        log("[Captcha Solver] 正在进行验证码识别...")
        solved = captcha_solver(captcha_image_url, session)
        if not solved or not solved.get("result"):
            log("未能从API获取有效结果。")
            return "-1", session
        captcha_code = solved["result"]
        log(f"[Captcha Solver] API识别的验证码是: {captcha_code}")

        f2 = session.post(url, headers=headers, proxies=PROXIES, data={"subaction": "login", "sess_id": sess_id, "captcha_code": captcha_code})
        if "To finish the login process please solve the following captcha." not in f2.text:
            log("验证通过")
            return sess_id, session
        else:
            log("验证失败")
            return "-1", session
    return sess_id, session

def get_servers(sess_id: str, session: requests.session) -> dict:
    """Gets all servers and their renewal status."""
    d, url = {}, f"https://support.euserv.com/index.iphp?sess_id={sess_id}"
    headers = {"user-agent": USER_AGENT, "origin": "https://www.euserv.com"}

    f = session.get(url=url, headers=headers, proxies=PROXIES)
    f.raise_for_status()
    soup = BeautifulSoup(f.text, "html.parser")

    for tr in soup.select("#kc2_order_customer_orders_tab_content_1 .kc2_order_table.kc2_content_table tr"):
        server_id_tag = tr.select_one(".td-z1-sp1-kc")
        action_container = tr.select_one(".td-z1-sp2-kc .kc2_order_action_container")
        if server_id_tag and server_id_tag.get_text(strip=True):
            server_id = server_id_tag.get_text(strip=True)
            action_text = action_container.get_text(strip=True)
            
            # The final, correct logic to determine renewal status.
            can_renew = action_text != '' and "Contract extension possible from" not in action_text
            d[server_id] = can_renew
    return d

def renew(username: str, password: str, order_id: str, mailparser_dl_url_id: str) -> bool:
    """Performs the complete renewal process in a fresh, dedicated session."""
    log("为确保会话状态最新，正在为本次续订执行一次全新的登录...")
    sess_id, session = login(username, password)
    if sess_id == "-1":
        log("续订前的登录失败。")
        return False

    url, headers = "https://support.euserv.com/index.iphp", {"user-agent": USER_AGENT, "Host": "support.euserv.com", "origin": "https://support.euserv.com", "Referer": "https://support.euserv.com/index.iphp"}

    session.post(url, headers=headers, data={"Submit": "Extend contract", "sess_id": sess_id, "ord_no": order_id, "subaction": "choose_order", "choose_order_subaction": "show_contract_details"}, proxies=PROXIES)
    session.post(url, headers=headers, proxies=PROXIES, data={"sess_id": sess_id, "subaction": "show_kc2_security_password_dialog", "prefix": "kc2_customer_contract_details_extend_contract_", "type": "1"})

    pin = get_pin_with_polling_and_comparison(mailparser_dl_url_id)
    if not pin:
        log("未能获取到PIN，续订中止。")
        return False

    data_pin = {"auth": pin, "sess_id": sess_id, "subaction": "kc2_security_password_get_token", "prefix": "kc2_customer_contract_details_extend_contract_", "type": "1", "ident": f"kc2_customer_contract_details_extend_contract_{order_id}"}
    f = session.post(url, headers=headers, data=data_pin, proxies=PROXIES)
    f.raise_for_status()
    response_json = f.json()

    if response_json.get("rs") != "success":
        log(f"PIN 验证失败: {response_json.get('rs', '未知错误')}")
        return False

    token = response_json["token"]["value"]
    data_renew = {"sess_id": sess_id, "ord_id": order_id, "subaction": "kc2_customer_contract_details_extend_contract_term", "token": token}
    session.post(url, headers=headers, data=data_renew, proxies=PROXIES)
    time.sleep(5)
    return True

def check(username: str, password: str):
    """Logs in and checks the final status of all servers."""
    log("正在检查续期后的状态...")
    sess_id, session = login(username, password)
    if sess_id == "-1":
        log("检查状态时登录失败。")
        return

    d = get_servers(sess_id, session)
    all_ok = all(not val for val in d.values())
    if not all_ok:
        for key, val in d.items():
            if val:
                log(f"ServerID: {key} 续期后检查发现仍可续期，可能失败了!")
    else:
        log("所有工作完成！尽情享受~")

def telegram():
    """Sends the final log digest to Telegram."""
    safe_desp = html.escape(desp)
    message = (
        "<b>AutoEUServerless 日志</b>\n\n"
        f"<pre>{safe_desp}</pre>"
        "\n<b>版权声明：</b>\n"
        "本脚本基于 GPL-3.0 许可协议，版权所有。\n\n"
        "<b>致谢：</b>\n"
        "特别感谢 <a href='https://github.com/lw9726/eu_ex'>eu_ex</a> 的贡献和启发, 本项目在此基础整理。\n"
        "开发者：<a href='https://github.com/WizisCool/AutoEUServerless'>WizisCool</a>\n"
        "<a href='https://www.nodeseek.com/space/8902#/general'>个人Nodeseek主页</a>\n"
        "<a href='https://dooo.ng'>个人小站Dooo.ng</a>\n\n"
        "<b>支持项目：</b>\n"
        "⭐️ 给我们一个 GitHub Star! ⭐️\n"
        "<a href='https://github.com/WizisCool/AutoEUServerless'>访问 GitHub 项目</a>"
    )
    data = {"chat_id": TG_USER_ID, "text": message, "parse_mode": "HTML", "disable_web_page_preview": "true"}
    try:
        response = requests.post(f"{TG_API_HOST}/bot{TG_BOT_TOKEN}/sendMessage", data=data, proxies=PROXIES, timeout=10)
        if response.status_code == 200:
            print("Telegram Bot 推送成功")
        else:
            print(f"Telegram Bot 推送失败: {response.text}")
    except Exception as e:
        print(f"Telegram Bot 推送异常: {e}")

# =====================================================================================
# Main Execution
# =====================================================================================
def main():
    """Main function to orchestrate the entire process."""
    if not all([USERNAME, PASSWORD, MAILPARSER_DOWNLOAD_URL_ID, OPENAI_API_KEY]):
        log("必要配置不完整!");
        return

    user_list = USERNAME.strip().split()
    passwd_list = PASSWORD.strip().split()
    mailparser_list = MAILPARSER_DOWNLOAD_URL_ID.strip().split()

    if not (len(user_list) == len(passwd_list) == len(mailparser_list)):
        log("账号、密码、Mailparser ID 数量不匹配!");
        return

    for i, user in enumerate(user_list):
        print("*" * 40)
        log(f"===> 开始处理第 {i + 1}/{len(user_list)} 个账号: {user} <===")

        # Step 1: Login to check for servers that need renewal.
        log("步骤 1/2: 检查服务器续订状态...")
        sessid, s = login(user, passwd_list[i])
        if sessid == "-1":
            log(f"第 {i + 1} 个账号登陆失败")
            continue
        log(f"账号 {user} 登录成功")
        servers = get_servers(sessid, s)
        log(f"检测到账号下有 {len(servers)} 台 VPS")

        # Step 2: For each server that needs renewal, run the independent renewal process.
        log("步骤 2/2: 开始执行续订任务...")
        if not servers:
            log("未找到任何 VPS。")
        else:
            renew_needed = False
            for server_id, can_renew in servers.items():
                if can_renew:
                    renew_needed = True
                    log(f"--- 正在处理 ServerID: {server_id} ---")
                    if not renew(user, passwd_list[i], server_id, mailparser_list[i]):
                        log(f"--- ServerID: {server_id} 续订错误! ---")
                    else:
                        log(f"--- ServerID: {server_id} 已成功续订! ---")
                else:
                    log(f"✅ --- ServerID: {server_id} 无需更新 ---")
            if not renew_needed:
                log("所有服务器均无需续订。")

        # Step 3: Final check after all renewals are done.
        time.sleep(5)
        check(user, passwd_list[i])

    log("所有账号处理完毕。")
    if TG_BOT_TOKEN and TG_USER_ID:
        telegram()
    print("*" * 40)


if __name__ == "__main__":
    main()
