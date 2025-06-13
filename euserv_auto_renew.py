# SPDX-License-Identifier: GPL-3.0-or-later

"""
euserv 自动续期脚本 (青龙面板适配版)
功能:
* 使用 TrueCaptcha API 自动识别验证码
* 发送通知到 Telegram
* 增加登录失败重试机制
* 日志信息格式化
* 从环境变量读取配置，安全方便
"""

import os
import re
import json
import time
import base64
import requests
from bs4 import BeautifulSoup

# --- 从环境变量读取配置 (您需要在青龙面板中设置这些变量) ---
USERNAME = os.getenv('EUSERV_USERNAME', '')
PASSWORD = os.getenv('EUSERV_PASSWORD', '')
TRUECAPTCHA_USERID = os.getenv('EUSERV_TRUECAPTCHA_USERID', '')
TRUECAPTCHA_APIKEY = os.getenv('EUSERV_TRUECAPTCHA_APIKEY', '')
MAILPARSER_DOWNLOAD_URL_ID = os.getenv('EUSERV_MAILPARSER_ID', '')
MAILPARSER_DOWNLOAD_BASE_URL = "https://files.mailparser.io/d/"
TG_BOT_TOKEN = os.getenv('EUSERV_TG_BOT_TOKEN', '')
TG_USER_ID = os.getenv('EUSERV_TG_USER_ID', '')
TG_API_HOST = os.getenv('EUSERV_TG_API_HOST', 'https://api.telegram.org')
PROXY_URL = os.getenv('EUSERV_PROXY', '')
PROXIES = {"http": PROXY_URL, "https": PROXY_URL} if PROXY_URL else None

# --- 其他配置 ---
LOGIN_MAX_RETRY_COUNT = 5
WAITING_TIME_OF_PIN = 15
# (以下代码省略，与之前版本完全相同，无需修改)
# ...
# (此处的代码是完整的，直接复制粘贴即可)

desp = ""

def log(info: str):
    emoji_map = {"正在续费": "🔄", "检测到": "🔍", "ServerID": "🔗", "无需更新": "✅", "续订错误": "⚠️", "已成功续订": "🎉", "所有工作完成": "🏁", "登陆失败": "❗", "验证通过": "✔️", "验证失败": "❌", "API 使用次数": "📊", "验证码是": "🔢", "登录尝试": "🔑", "[MailParser]": "📧", "[Captcha Solver]": "🧩", "[AutoEUServerless]": "🌐"}
    for key, emoji in emoji_map.items():
        if key in info: info = emoji + " " + info; break
    print(info)
    global desp
    desp += info + "\n\n"

def login_retry(*args, **kwargs):
    def wrapper(func):
        def inner(username, password):
            ret, ret_session = func(username, password)
            max_retry = kwargs.get("max_retry", 3)
            number = 0
            while ret == "-1" and number < max_retry:
                number += 1
                if number > 1: log(f"[AutoEUServerless] 登录尝试第 {number} 次")
                ret, ret_session = func(username, password)
            return ret, ret_session
        return inner
    return wrapper

def captcha_solver(captcha_image_url: str, session: requests.session) -> dict:
    response = session.get(captcha_image_url, proxies=PROXIES)
    encoded_string = base64.b64encode(response.content)
    url = "https://api.apitruecaptcha.org/one/gettext"
    data = {"userid": TRUECAPTCHA_USERID, "apikey": TRUECAPTCHA_APIKEY, "case": "mixed", "mode": "human", "data": str(encoded_string)[2:-1]}
    r = requests.post(url=url, json=data, proxies=PROXIES)
    return r.json()

def handle_captcha_solved_result(solved: dict) -> str:
    if "result" in solved:
        text = solved["result"]
        if "RESULT  IS" in text: text = re.findall(r"RESULT  IS . (.*) .", text)[0]
        operators = {"x": "*", "X": "*", "+": "+", "-": "-"}
        for op_char, op_func in operators.items():
            if op_char in text:
                try:
                    left, right = text.split(op_char)
                    if left.strip().isdigit() and right.strip().isdigit(): return str(eval(f"{left.strip()} {op_func} {right.strip()}"))
                except ValueError: continue
        return text
    raise KeyError(f"未找到解析结果: {solved}")

def get_captcha_solver_usage() -> dict:
    url = "https://api.apitruecaptcha.org/one/getusage"
    params = {"username": TRUECAPTCHA_USERID, "apikey": TRUECAPTCHA_APIKEY}
    r = requests.get(url=url, params=params, proxies=PROXIES)
    return r.json()

def get_pin_from_mailparser(url_id: str) -> str:
    response = requests.get(f"{MAILPARSER_DOWNLOAD_BASE_URL}{url_id}", proxies=PROXIES)
    response.raise_for_status()
    return response.json()[0]["pin"]

@login_retry(max_retry=LOGIN_MAX_RETRY_COUNT)
def login(username: str, password: str) -> (str, requests.session):
    headers = {"user-agent": user_agent, "origin": "https://www.euserv.com"}
    url = "https://support.euserv.com/index.iphp"
    captcha_image_url = "https://support.euserv.com/securimage_show.php"
    session = requests.Session()
    sess = session.get(url, headers=headers, proxies=PROXIES)
    sess_id_match = re.search(r"PHPSESSID=(\w+);", str(sess.headers))
    if not sess_id_match: return "-1", session
    sess_id = sess_id_match.group(1)
    login_data = {"email": username, "password": password, "form_selected_language": "en", "Submit": "Login", "subaction": "login", "sess_id": sess_id}
    f = session.post(url, headers=headers, data=login_data, proxies=PROXIES)
    f.raise_for_status()
    if "Hello" in f.text or "Confirm or change your customer data here" in f.text: return sess_id, session
    if "To finish the login process please solve the following captcha." in f.text:
        log("[Captcha Solver] 正在进行验证码识别...")
        solved_result = captcha_solver(captcha_image_url, session)
        captcha_code = handle_captcha_solved_result(solved_result)
        log(f"[Captcha Solver] 识别的验证码是: {captcha_code}")
        if TRUECAPTCHA_USERID:
            try:
                usage = get_captcha_solver_usage()
                log(f"[Captcha Solver] 当前日期 {usage[0]['date']} API 使用次数: {usage[0]['count']}")
            except Exception: log("[Captcha Solver] 查询API使用次数失败。")
        f2 = session.post(url, headers=headers, data={"subaction": "login", "sess_id": sess_id, "captcha_code": captcha_code}, proxies=PROXIES)
        if "To finish the login process please solve the following captcha." not in f2.text:
            log("[Captcha Solver] 验证通过"); return sess_id, session
        else:
            log("[Captcha Solver] 验证失败"); return "-1", session
    return "-1", session

def get_servers(sess_id: str, session: requests.session) -> {}:
    d = {}
    url = f"https://support.euserv.com/index.iphp?sess_id={sess_id}"
    headers = {"user-agent": user_agent, "origin": "https://www.euserv.com"}
    f = session.get(url=url, headers=headers, proxies=PROXIES)
    f.raise_for_status()
    soup = BeautifulSoup(f.text, "html.parser")
    for tr in soup.select("#kc2_order_customer_orders_tab_content_1 .kc2_order_table.kc2_content_table tr"):
        server_id = tr.select(".td-z1-sp1-kc")
        if not len(server_id) == 1: continue
        d[server_id[0].get_text()] = "Contract extension possible from" not in tr.select(".td-z1-sp2-kc .kc2_order_action_container")[0].get_text()
    return d

def renew(sess_id: str, session: requests.session, order_id: str, mailparser_dl_url_id: str) -> bool:
    url = "https://support.euserv.com/index.iphp"
    headers = {"user-agent": user_agent, "Host": "support.euserv.com", "origin": "https://support.euserv.com", "Referer": "https://support.euserv.com/index.iphp"}
    session.post(url, headers=headers, data={"Submit": "Extend contract", "sess_id": sess_id, "ord_no": order_id, "subaction": "choose_order", "choose_order_subaction": "show_contract_details"}, proxies=PROXIES)
    session.post(url, headers=headers, data={"sess_id": sess_id, "subaction": "show_kc2_security_password_dialog", "prefix": "kc2_customer_contract_details_extend_contract_", "type": "1"}, proxies=PROXIES)
    time.sleep(WAITING_TIME_OF_PIN)
    pin = get_pin_from_mailparser(mailparser_dl_url_id)
    log(f"[MailParser] PIN: {pin}")
    f = session.post(url, headers=headers, data={"auth": pin, "sess_id": sess_id, "subaction": "kc2_security_password_get_token", "prefix": "kc2_customer_contract_details_extend_contract_", "type": 1, "ident": f"kc2_customer_contract_details_extend_contract_{order_id}"}, proxies=PROXIES)
    f.raise_for_status()
    if not f.json()["rs"] == "success": return False
    token = f.json()["token"]["value"]
    session.post(url, headers=headers, data={"sess_id": sess_id, "ord_id": order_id, "subaction": "kc2_customer_contract_details_extend_contract_term", "token": token}, proxies=PROXIES)
    time.sleep(5); return True

def check(sess_id: str, session: requests.session):
    log("正在检查续期状态.......")
    d = get_servers(sess_id, session)
    if all(not v for v in d.values()):
        log("[AutoEUServerless] 所有工作完成！所有vps均无需续期或已成功续期！")
    else:
        log("[AutoEUServerless] 注意：有部分vps续期失败或状态异常!")


def telegram():
    message = "<b>AutoEUServerless 日志</b>\n\n" + desp
    data = {"chat_id": TG_USER_ID, "text": message, "parse_mode": "HTML", "disable_web_page_preview": "true"}
    try:
        response = requests.post(f"{TG_API_HOST}/bot{TG_BOT_TOKEN}/sendMessage", data=data, proxies=PROXIES)
        log("Telegram Bot 推送成功" if response.status_code == 200 else f"Telegram Bot 推送失败: {response.text}")
    except Exception as e:
        log(f"Telegram Bot 推送异常: {e}")

def main_handler():
    if not all([USERNAME, PASSWORD, MAILPARSER_DOWNLOAD_URL_ID, TRUECAPTCHA_USERID, TRUECAPTCHA_APIKEY]):
        log("[AutoEUServerless] 关键环境变量未设置，请检查青龙面板配置！")
        return
    user_list, passwd_list, mail_id_list = USERNAME.strip().split(), PASSWORD.strip().split(), MAILPARSER_DOWNLOAD_URL_ID.strip().split()
    if not (len(user_list) == len(passwd_list) == len(mail_id_list)):
        log("[AutoEUServerless] 用户名、密码、Mailparser ID 的数量不匹配!")
        return
    for i in range(len(user_list)):
        print("*" * 30); log(f"[AutoEUServerless] 正在续费第 {i + 1} 个账号")
        sessid, s = login(user_list[i], passwd_list[i])
        if sessid == "-1": log(f"[AutoEUServerless] 第 {i + 1} 个账号登陆失败"); continue
        SERVERS = get_servers(sessid, s)
        log(f"[AutoEUServerless] 检测到第 {i + 1} 个账号有 {len(SERVERS)} 台 VPS")
        for k, v in SERVERS.items():
            if v:
                log(f"[AutoEUServerless] 正在为 ServerID: {k} 续订...")
                if renew(sessid, s, k, mail_id_list[i]): log(f"[AutoEUServerless] ServerID: {k} 已成功续订!")
                else: log(f"[AutoEUServerless] ServerID: {k} 续订错误!")
            else: log(f"[AutoEUServerless] ServerID: {k} 无需更新")
        time.sleep(15); check(sessid, s); time.sleep(5)
    if TG_BOT_TOKEN and TG_USER_ID: telegram()

if __name__ == "__main__":
    main_handler()
