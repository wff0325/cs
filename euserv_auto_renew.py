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
TG_BOT_TOKEN = os.getenv('EUSERV_TG_BOT_TOKEN', '')
TG_USER_ID = os.getenv('EUSERV_TG_USER_ID', '')
TG_API_HOST = os.getenv('EUSERV_TG_API_HOST', 'https://api.telegram.org')
PROXY_URL = os.getenv('EUSERV_PROXY', '')

# --- 全局配置和变量 (修复 NameError 的关键部分) ---
PROXIES = {"http": PROXY_URL, "https": PROXY_URL} if PROXY_URL else None
LOGIN_MAX_RETRY_COUNT = 5
WAITING_TIME_OF_PIN = 15
CHECK_CAPTCHA_SOLVER_USAGE = True
MAILPARSER_DOWNLOAD_BASE_URL = "https://files.mailparser.io/d/"

# 这个就是之前缺失的变量
user_agent = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/108.0.0.0 Safari/537.36"
)

# 全局日志变量
desp = ""

# --- 函数定义 ---

def log(info: str):
    """打印并记录日志信息"""
    emoji_map = {"正在续费": "🔄", "检测到": "🔍", "ServerID": "🔗", "无需更新": "✅", "续订错误": "⚠️", "已成功续订": "🎉", "所有工作完成": "🏁", "登陆失败": "❗", "验证通过": "✔️", "验证失败": "❌", "API 使用次数": "📊", "验证码是": "🔢", "登录尝试": "🔑", "[MailParser]": "📧", "[Captcha Solver]": "🧩", "[AutoEUServerless]": "🌐"}
    for key, emoji in emoji_map.items():
        if key in info:
            info = f"{emoji} {info}"
            break
    print(info)
    global desp
    desp += info + "\n\n"

def login_retry(max_retry):
    """登录重试装饰器"""
    def decorator(func):
        def wrapper(*args, **kwargs):
            for i in range(max_retry):
                if i > 0:
                    log(f"[AutoEUServerless] 登录尝试第 {i + 1} 次")
                sess_id, session = func(*args, **kwargs)
                if sess_id != "-1":
                    return sess_id, session
                time.sleep(3) # 失败后等待3秒再重试
            return "-1", None
        return wrapper
    return decorator

def captcha_solver(captcha_image_url: str, session: requests.session) -> dict:
    """验证码解决器"""
    try:
        response = session.get(captcha_image_url, proxies=PROXIES)
        response.raise_for_status()
        encoded_string = base64.b64encode(response.content).decode('utf-8')
        url = "https://api.apitruecaptcha.org/one/gettext"
        data = {"userid": TRUECAPTCHA_USERID, "apikey": TRUECAPTCHA_APIKEY, "case": "mixed", "mode": "human", "data": encoded_string}
        r = requests.post(url=url, json=data, proxies=PROXIES, timeout=30)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        log(f"[Captcha Solver] 请求验证码识别时出错: {e}")
        return {}

def handle_captcha_solved_result(solved: dict) -> str:
    """处理验证码解决结果"""
    if "result" in solved:
        text = solved["result"]
        log(f"[Captcha Solver] 原始识别结果: {text}")
        # 尝试计算表达式
        try:
            # 替换 'x' 为 '*' 并移除所有非数字和非运算符字符
            text_eval = re.sub(r'[^\d\+\-\*\/]', '', text.lower().replace('x', '*'))
            if re.match(r'^\d+[\+\-\*\/]\d+$', text_eval):
                return str(eval(text_eval))
        except Exception:
            pass # 如果计算失败，则返回原始文本
        return text
    log(f"[Captcha Solver] 错误，未找到识别结果: {solved}")
    return ""

@login_retry(max_retry=LOGIN_MAX_RETRY_COUNT)
def login(username: str, password: str) -> (str, requests.session):
    """登录 EUserv 并获取 session"""
    headers = {"user-agent": user_agent, "origin": "https://www.euserv.com"}
    url = "https://support.euserv.com/index.iphp"
    session = requests.Session()

    try:
        # 获取会话ID
        sess = session.get(url, headers=headers, proxies=PROXIES)
        sess.raise_for_status()
        sess_id_match = re.search(r'name="sess_id" value="(\w+)"', sess.text)
        if not sess_id_match:
            log("[AutoEUServerless] 登录失败：无法获取 sess_id")
            return "-1", session
        sess_id = sess_id_match.group(1)

        # 提交登录表单
        login_data = {"email": username, "password": password, "form_selected_language": "en", "Submit": "Login", "subaction": "login", "sess_id": sess_id}
        f = session.post(url, headers=headers, data=login_data, proxies=PROXIES)
        f.raise_for_status()

        # 检查是否需要验证码
        if "To finish the login process please solve the following captcha." in f.text:
            log("[Captcha Solver] 检测到需要验证码，正在识别...")
            captcha_image_url = "https://support.euserv.com/securimage_show.php"
            solved_result = captcha_solver(captcha_image_url, session)
            captcha_code = handle_captcha_solved_result(solved_result)
            if not captcha_code:
                log("[Captcha Solver] 验证码识别失败")
                return "-1", session
            log(f"[Captcha Solver] 识别的验证码是: {captcha_code}")

            # 提交验证码
            f2 = session.post(url, headers=headers, data={"subaction": "login", "sess_id": sess_id, "captcha_code": captcha_code}, proxies=PROXIES)
            if "captcha was entered incorrectly" in f2.text:
                log("[Captcha Solver] 验证失败: 验证码错误")
                return "-1", session
            log("[Captcha Solver] 验证通过")
        
        # 验证最终登录状态
        final_page = session.get(f"https://support.euserv.com/index.iphp?sess_id={sess_id}", headers=headers, proxies=PROXIES)
        if "Hello" in final_page.text or "customer data" in final_page.text:
            log("[AutoEUServerless] 登录成功")
            return sess_id, session
        else:
            log("[AutoEUServerless] 登录失败，未找到成功标识")
            return "-1", session

    except requests.exceptions.RequestException as e:
        log(f"[AutoEUServerless] 登录请求异常: {e}")
        return "-1", session

def get_servers(sess_id: str, session: requests.session) -> dict:
    """获取服务器列表"""
    servers = {}
    try:
        url = f"https://support.euserv.com/index.iphp?sess_id={sess_id}"
        headers = {"user-agent": user_agent, "origin": "https://www.euserv.com"}
        f = session.get(url=url, headers=headers, proxies=PROXIES)
        f.raise_for_status()
        soup = BeautifulSoup(f.text, "html.parser")
        for tr in soup.select("#kc2_order_customer_orders_tab_content_1 .kc2_order_table tr"):
            server_id_tag = tr.select_one(".td-z1-sp1-kc")
            action_tag = tr.select_one(".td-z1-sp2-kc .kc2_order_action_container")
            if server_id_tag and action_tag:
                server_id = server_id_tag.get_text(strip=True)
                # 如果文本中不包含 "possible from"，说明可以续期
                can_renew = "possible from" not in action_tag.get_text()
                servers[server_id] = can_renew
    except Exception as e:
        log(f"[AutoEUServerless] 获取服务器列表时出错: {e}")
    return servers

def renew(sess_id: str, session: requests.session, order_id: str, mailparser_id: str) -> bool:
    """执行续期操作"""
    # 此函数较为复杂，暂时保留原样，确保核心逻辑不变
    # 后续可以增加更多错误处理
    try:
        url = "https://support.euserv.com/index.iphp"
        headers = {"user-agent": user_agent, "origin": "https://support.euserv.com", "Referer": "https://support.euserv.com/index.iphp"}
        session.post(url, headers=headers, data={"Submit": "Extend contract", "sess_id": sess_id, "ord_no": order_id, "subaction": "choose_order", "choose_order_subaction": "show_contract_details"}, proxies=PROXIES)
        session.post(url, headers=headers, data={"sess_id": sess_id, "subaction": "show_kc2_security_password_dialog", "prefix": "kc2_customer_contract_details_extend_contract_", "type": "1"}, proxies=PROXIES)
        
        log(f"[MailParser] 等待 {WAITING_TIME_OF_PIN} 秒以获取 PIN...")
        time.sleep(WAITING_TIME_OF_PIN)
        pin_response = requests.get(f"{MAILPARSER_DOWNLOAD_BASE_URL}{mailparser_id}", proxies=PROXIES)
        pin_response.raise_for_status()
        pin = pin_response.json()[0]["pin"]
        log(f"[MailParser] 获取到 PIN: {pin}")
        
        token_data = {"auth": pin, "sess_id": sess_id, "subaction": "kc2_security_password_get_token", "prefix": "kc2_customer_contract_details_extend_contract_", "type": 1, "ident": f"kc2_customer_contract_details_extend_contract_{order_id}"}
        token_res = session.post(url, headers=headers, data=token_data, proxies=PROXIES)
        token_res.raise_for_status()
        if token_res.json().get("rs") != "success":
            log("[AutoEUServerless] 获取续期 token 失败")
            return False
        
        token = token_res.json()["token"]["value"]
        renew_data = {"sess_id": sess_id, "ord_id": order_id, "subaction": "kc2_customer_contract_details_extend_contract_term", "token": token}
        session.post(url, headers=headers, data=renew_data, proxies=PROXIES)
        time.sleep(5)
        return True
    except Exception as e:
        log(f"[AutoEUServerless] 续期 ServerID: {order_id} 时出错: {e}")
        return False


def telegram():
    """发送 Telegram 通知"""
    if not TG_BOT_TOKEN or not TG_USER_ID:
        return
    message = "<b>AutoEUServerless 续期日志</b>\n\n" + desp
    data = {"chat_id": TG_USER_ID, "text": message, "parse_mode": "HTML", "disable_web_page_preview": "true"}
    try:
        response = requests.post(f"{TG_API_HOST.rstrip('/')}/bot{TG_BOT_TOKEN}/sendMessage", data=data, proxies=PROXIES)
        if response.status_code == 200:
            print("Telegram Bot 推送成功")
        else:
            print(f"Telegram Bot 推送失败: {response.text}")
    except Exception as e:
        print(f"Telegram Bot 推送异常: {e}")

def main_handler():
    """主函数"""
    if not all([USERNAME, PASSWORD, MAILPARSER_DOWNLOAD_URL_ID, TRUECAPTCHA_USERID, TRUECAPTCHA_APIKEY]):
        log("[AutoEUServerless] 关键环境变量未设置，请检查青龙面板配置！")
        return

    user_list = USERNAME.strip().split()
    passwd_list = PASSWORD.strip().split()
    mail_id_list = MAILPARSER_DOWNLOAD_URL_ID.strip().split()

    if not (len(user_list) == len(passwd_list) == len(mail_id_list)):
        log("[AutoEUServerless] 用户名、密码、Mailparser ID 的数量不匹配!")
        return

    for i in range(len(user_list)):
        print("*" * 40)
        log(f"[AutoEUServerless] 正在处理第 {i + 1} 个账号: {user_list[i]}")
        sessid, s = login(user_list[i], passwd_list[i])
        
        if sessid == "-1" or s is None:
            log(f"[AutoEUServerless] 第 {i + 1} 个账号登陆失败，跳过此账号")
            continue
            
        servers = get_servers(sessid, s)
        log(f"[AutoEUServerless] 检测到 {len(servers)} 台 VPS")

        all_ok = True
        for server_id, can_renew in servers.items():
            if can_renew:
                log(f"[AutoEUServerless] 正在为 ServerID: {server_id} 续订...")
                if renew(sessid, s, server_id, mail_id_list[i]):
                    log(f"🎉 [AutoEUServerless] ServerID: {server_id} 已成功续订!")
                else:
                    log(f"⚠️ [AutoEUServerless] ServerID: {server_id} 续订错误!")
                    all_ok = False
            else:
                log(f"✅ [AutoEUServerless] ServerID: {server_id} 无需更新")
        
        if all_ok:
            log("🏁 [AutoEUServerless] 所有工作完成！")

    telegram()

if __name__ == "__main__":
    main_handler()
