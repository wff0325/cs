# SPDX-License-Identifier: GPL-3.0-or-later

# =======================================================================================
# 青龙面板 使用说明
#
# 1. 依赖管理:
#    - 在青龙面板的 "依赖管理" -> "Python3" 中，添加以下两个依赖，然后等待安装完成:
#      - requests
#      - beautifulsoup4
#
# 2. 环境变量: (请务必检查，不要有遗漏或多余的空格)
#    - 在青龙面板的 "环境变量" 中，添加以下变量。
#    - 多账号的值之间用【单个空格】隔开，且 USERNAME, PASSWORD, MAILPARSER_DOWNLOAD_URL_ID 三者的顺序和数量必须一一对应。
#
#    -----------------------------------------------------------------------------------
#    | 名称                        | 值                                                 | 备注                                         |
#    |-----------------------------|----------------------------------------------------|----------------------------------------------|
#    | USERNAME                    | 你的EUserV客户ID或邮箱 (多个用空格隔开)              | 【必填】                                       |
#    | PASSWORD                    | 你的EUserV密码 (多个用空格隔开)                      | 【必填】                                       |
#    | TRUECAPTCHA_USERID          | 你的TrueCaptcha UserID                             | 【必填】验证码识别服务，申请: truecaptcha.org |
#    | TRUECAPTCHA_APIKEY          | 你的TrueCaptcha APIKEY                             | 【必填】                                       |
#    | MAILPARSER_DOWNLOAD_URL_ID  | 你的Mailparser下载URL_ID (多个用空格隔开)         | 【必填】用于接收PIN码                         |
#    | TG_BOT_TOKEN                | 你的Telegram机器人Token                            | 【可选】用于发送通知                           |
#    | TG_USER_ID                  | 你的Telegram用户ID                                 | 【可选】用于发送通知                           |
#    | PROXIES                     | 代理地址, 例如: http://127.0.0.1:10808             | 【可选】如果你的网络环境需要代理              |
#    -----------------------------------------------------------------------------------
#
# =======================================================================================

"""
euserv 自动续期脚本 (Robust Version)
功能:
* 使用 TrueCaptcha API 自动识别验证码
* 发送通知到 Telegram
* 增加登录失败重试机制
* 日志信息格式化
* 全面的错误处理和网络超时
"""

import os
import re
import json
import time
import base64
import requests
from bs4 import BeautifulSoup

# --- 配置信息 (优先从环境变量读取) ---

# 账户信息：用户名和密码 (多个账号用空格隔开)
USERNAME = os.environ.get('USERNAME', '')
PASSWORD = os.environ.get('PASSWORD', '')

# TrueCaptcha API 配置 (申请地址: https://truecaptcha.org/)
TRUECAPTCHA_USERID = os.environ.get('TRUECAPTCHA_USERID', '')
TRUECAPTCHA_APIKEY = os.environ.get('TRUECAPTCHA_APIKEY', '')

# Mailparser 配置 (多个ID用空格隔开)
MAILPARSER_DOWNLOAD_URL_ID = os.environ.get('MAILPARSER_DOWNLOAD_URL_ID', '')
MAILPARSER_DOWNLOAD_BASE_URL = "https://files.mailparser.io/d/"  # 无需更改除非你要反代

# Telegram Bot 推送配置
TG_BOT_TOKEN = os.environ.get('TG_BOT_TOKEN', "")
TG_USER_ID = os.environ.get('TG_USER_ID', "")
TG_API_HOST = os.environ.get('TG_API_HOST', "https://api.telegram.org")

# 代理设置（如果需要）
_proxy_url = os.environ.get("PROXIES")
PROXIES = {"http": _proxy_url, "https": _proxy_url} if _proxy_url else None

# --- 常量设置 ---
LOGIN_MAX_RETRY_COUNT = 3  # 最大登录重试次数调整为3次，避免过长时间等待
WAITING_TIME_OF_PIN = 20   # 接收 PIN 的等待时间，单位为秒，适当延长以防邮件延迟
CHECK_CAPTCHA_SOLVER_USAGE = True
REQUEST_TIMEOUT = 30       # 网络请求超时时间
user_agent = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/108.0.0.0 Safari/537.36"
)

desp = ""  # 日志信息

def log(info: str):
    # 打印并记录日志信息
    formatted_info = f"[{time.strftime('%Y-%m-%d %H:%M:%S', time.localtime())}] {info}"
    print(formatted_info)
    global desp
    desp += formatted_info + "\n\n"


# 登录重试装饰器
def login_retry(max_retry=3):
    def decorator(func):
        def wrapper(*args, **kwargs):
            for i in range(max_retry):
                try:
                    sess_id, session = func(*args, **kwargs)
                    if sess_id != "-1":
                        return sess_id, session
                    log(f"登录尝试 {i + 1}/{max_retry} 失败，稍后重试...")
                except Exception as e:
                    log(f"登录尝试 {i + 1}/{max_retry} 出现异常: {e}")
                if i < max_retry - 1:
                    time.sleep(5)
            log("所有登录尝试均失败。")
            return "-1", None
        return wrapper
    return decorator

# 验证码解决器
def captcha_solver(captcha_image_url: str, session: requests.session) -> dict:
    url = "https://api.apitruecaptcha.org/one/gettext"
    try:
        response = session.get(captcha_image_url, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
        encoded_string = base64.b64encode(response.content)

        data = {
            "userid": TRUECAPTCHA_USERID,
            "apikey": TRUECAPTCHA_APIKEY, "case": "mixed", "mode": "human",
            "data": str(encoded_string)[2:-1],
        }
        r = requests.post(url=url, json=data, proxies=PROXIES, timeout=REQUEST_TIMEOUT)
        r.raise_for_status()
        return r.json()
    except requests.exceptions.RequestException as e:
        log(f"❌ [Captcha Solver] 网络请求失败: {e}")
    except json.JSONDecodeError:
        log(f"❌ [Captcha Solver] API响应非JSON格式: {r.text}")
    except Exception as e:
        log(f"❌ [Captcha Solver] 未知错误: {e}")
    return {}

# 处理验证码解决结果
def handle_captcha_solved_result(solved: dict) -> str:
    if not solved or "result" not in solved:
        log("❌ [Captcha Solver] 未收到有效的解析结果。")
        return ""
    
    text = solved.get("result", "")
    log(f"🔢 [Captcha Solver] 原始识别结果: {text}")

    # 简单数学计算处理
    try:
        text = text.replace('x', '*').replace('X', '*')
        if any(op in text for op in ['+', '-', '*']):
            return str(eval(text))
    except Exception:
        # 如果eval失败，则返回原始文本
        pass
    return text

# 从 Mailparser 获取 PIN
def get_pin_from_mailparser(url_id: str) -> str:
    log(f"📧 [MailParser] 等待 {WAITING_TIME_OF_PIN} 秒以获取 PIN...")
    time.sleep(WAITING_TIME_OF_PIN)
    try:
        response = requests.get(
            f"{MAILPARSER_DOWNLOAD_BASE_URL}{url_id}",
            proxies=PROXIES, timeout=REQUEST_TIMEOUT
        )
        response.raise_for_status()
        data = response.json()
        if data and isinstance(data, list) and "pin" in data[0]:
            pin = data[0]["pin"]
            log(f"📧 [MailParser] 成功获取到 PIN: {pin}")
            return pin
        else:
            log(f"❌ [MailParser] 获取PIN失败，API返回数据格式不正确: {data}")
            return ""
    except requests.exceptions.RequestException as e:
        log(f"❌ [MailParser] 获取PIN网络请求失败: {e}")
    except (json.JSONDecodeError, IndexError, KeyError) as e:
        log(f"❌ [MailParser] 解析PIN数据失败: {e}")
    return ""


# 登录函数
@login_retry(max_retry=LOGIN_MAX_RETRY_COUNT)
def login(username: str, password: str) -> (str, requests.session):
    headers = {"user-agent": user_agent, "origin": "https://www.euserv.com"}
    url = "https://support.euserv.com/index.iphp"
    captcha_image_url = "https://support.euserv.com/securimage_show.php"
    
    session = requests.Session()
    if PROXIES:
        session.proxies.update(PROXIES)
    session.headers.update(headers)

    try:
        # 1. 获取 Session ID
        sess_resp = session.get(url, timeout=REQUEST_TIMEOUT)
        sess_resp.raise_for_status()
        match = re.search(r"PHPSESSID=(\w+);", sess_resp.headers.get('Set-Cookie', ''))
        if not match:
            log("❌ 无法从响应头中获取PHPSESSID。")
            return "-1", session
        sess_id = match.group(1)

        # 2. 尝试登录
        login_data = {
            "email": username, "password": password, "form_selected_language": "en",
            "Submit": "Login", "subaction": "login", "sess_id": sess_id,
        }
        f = session.post(url, data=login_data, timeout=REQUEST_TIMEOUT)
        f.raise_for_status()

        # 3. 检查是否需要验证码
        if "Hello" in f.text or "Confirm or change your customer data here" in f.text:
            log("✔️ 登录成功 (无需验证码)")
            return sess_id, session

        if "To finish the login process please solve the following captcha." not in f.text:
            log("❌ 登录失败，未知响应页面。请检查账号密码。")
            return "-1", session
        
        # 4. 处理验证码
        log("🧩 [Captcha Solver] 需要验证码，正在识别...")
        solved_result = captcha_solver(captcha_image_url, session)
        captcha_code = handle_captcha_solved_result(solved_result)
        if not captcha_code:
            return "-1", session

        f2 = session.post(
            url,
            data={"subaction": "login", "sess_id": sess_id, "captcha_code": captcha_code},
            timeout=REQUEST_TIMEOUT
        )
        f2.raise_for_status()

        if "To finish the login process please solve the following captcha." not in f2.text:
            log("✔️ 验证码验证通过，登录成功。")
            return sess_id, session
        else:
            log("❌ 验证码错误或已过期。")
            return "-1", session

    except requests.exceptions.RequestException as e:
        log(f"❌ 登录过程中网络错误: {e}")
        return "-1", session
    except Exception as e:
        log(f"❌ 登录过程中发生未知异常: {e}")
        return "-1", session

# 获取服务器列表
def get_servers(sess_id: str, session: requests.session) -> {}:
    d = {}
    url = f"https://support.euserv.com/index.iphp?sess_id={sess_id}"
    try:
        f = session.get(url=url, timeout=REQUEST_TIMEOUT)
        f.raise_for_status()
        soup = BeautifulSoup(f.text, "html.parser")
        rows = soup.select("#kc2_order_customer_orders_tab_content_1 .kc2_order_table.kc2_content_table tr")
        if not rows:
            log("🔍 未找到服务器列表。")
            return {}
            
        for tr in rows:
            server_id_tag = tr.select_one(".td-z1-sp1-kc")
            action_container = tr.select_one(".td-z1-sp2-kc .kc2_order_action_container")
            if not server_id_tag or not action_container:
                continue
            
            server_id = server_id_tag.get_text(strip=True)
            action_text = action_container.get_text()
            
            # 如果文本中不包含 "possible from"，说明可以续期
            can_renew = "Contract extension possible from" not in action_text
            d[server_id] = can_renew
        return d
    except requests.exceptions.RequestException as e:
        log(f"❌ 获取服务器列表网络失败: {e}")
    except Exception as e:
        log(f"❌ 解析服务器列表失败: {e}")
    return {}

# 续期操作
def renew(sess_id: str, session: requests.session, order_id: str, mailparser_dl_url_id: str) -> bool:
    url = "https://support.euserv.com/index.iphp"
    try:
        # 1. 触发续期流程
        session.post(url, data={
            "Submit": "Extend contract", "sess_id": sess_id, "ord_no": order_id,
            "subaction": "choose_order", "choose_order_subaction": "show_contract_details",
        }, timeout=REQUEST_TIMEOUT).raise_for_status()

        # 2. 触发发送PIN码
        session.post(url, data={
            "sess_id": sess_id, "subaction": "show_kc2_security_password_dialog",
            "prefix": "kc2_customer_contract_details_extend_contract_", "type": "1",
        }, timeout=REQUEST_TIMEOUT).raise_for_status()

        # 3. 获取PIN码
        pin = get_pin_from_mailparser(mailparser_dl_url_id)
        if not pin:
            return False

        # 4. 使用PIN获取Token
        token_resp = session.post(url, data={
            "auth": pin, "sess_id": sess_id, "subaction": "kc2_security_password_get_token",
            "prefix": "kc2_customer_contract_details_extend_contract_", "type": 1,
            "ident": f"kc2_customer_contract_details_extend_contract_{order_id}",
        }, timeout=REQUEST_TIMEOUT)
        token_resp.raise_for_status()
        token_data = token_resp.json()

        if token_data.get("rs") != "success":
            log(f"❌ 获取Token失败: {token_data.get('msg', '未知错误')}")
            return False
        
        token = token_data["token"]["value"]

        # 5. 执行续期
        renew_resp = session.post(url, data={
            "sess_id": sess_id, "ord_id": order_id,
            "subaction": "kc2_customer_contract_details_extend_contract_term", "token": token,
        }, timeout=REQUEST_TIMEOUT)
        renew_resp.raise_for_status()
        time.sleep(5)
        return True

    except requests.exceptions.RequestException as e:
        log(f"❌ 续期ServerID {order_id} 时网络失败: {e}")
    except (json.JSONDecodeError, KeyError) as e:
        log(f"❌ 续期ServerID {order_id} 时解析响应失败: {e}")
    except Exception as e:
        log(f"❌ 续期ServerID {order_id} 时发生未知错误: {e}")
    return False

# 检查续期状态
def check(sess_id: str, session: requests.session):
    log("🔄 正在检查续期后的状态...")
    d = get_servers(sess_id, session)
    if not d:
        log("⚠️ 无法获取服务器状态，检查已跳过。")
        return
        
    all_ok = True
    for key, val in d.items():
        if val: # 如果仍然可以续期，说明上次操作失败
            all_ok = False
            log(f"⚠️ ServerID: {key} 续期失败或状态未更新!")

    if all_ok:
        log("🏁 所有工作完成！VPS状态正常。")

# 发送 Telegram 通知
def telegram():
    if not all([TG_BOT_TOKEN, TG_USER_ID]):
        return
        
    message = f"<b>AutoEUServerless 运行日志</b>\n<pre>{desp}</pre>"
    data = {
        "chat_id": TG_USER_ID, "text": message,
        "parse_mode": "HTML", "disable_web_page_preview": "true"
    }
    try:
        response = requests.post(
            f"{TG_API_HOST}/bot{TG_BOT_TOKEN}/sendMessage",
            data=data, proxies=PROXIES, timeout=REQUEST_TIMEOUT
        )
        if response.status_code == 200:
            print("Telegram Bot 推送成功")
        else:
            print(f"Telegram Bot 推送失败: {response.text}")
    except Exception as e:
        print(f"Telegram Bot 推送异常: {e}")

def main_handler(event=None, context=None):
    if not all([USERNAME, PASSWORD, TRUECAPTCHA_USERID, TRUECAPTCHA_APIKEY, MAILPARSER_DOWNLOAD_URL_ID]):
        log("❌ 关键配置缺失，请在环境变量中正确填写所有必填项！")
        telegram()
        return

    user_list = USERNAME.strip().split()
    passwd_list = PASSWORD.strip().split()
    mailparser_id_list = MAILPARSER_DOWNLOAD_URL_ID.strip().split()

    if not (len(user_list) == len(passwd_list) == len(mailparser_id_list)):
        log("❌ 用户、密码和Mailparser ID的数量不匹配，请检查配置!")
        telegram()
        return

    for i, user in enumerate(user_list):
        log("="*30)
        log(f"🌐 正在处理第 {i + 1}/{len(user_list)} 个账号: {user}")
        
        sessid, s = login(user, passwd_list[i])
        if sessid == "-1" or not s:
            log(f"❗ 第 {i + 1} 个账号登陆彻底失败，跳过此账号。")
            continue
        
        SERVERS = get_servers(sessid, s)
        if not SERVERS:
            log(f"✅ 第 {i + 1} 个账号下没有找到VPS或无法获取列表，跳过续期。")
            continue
            
        log(f"🔍 检测到 {len(SERVERS)} 台 VPS，正在尝试续期...")
        for k, v in SERVERS.items():
            if v: # v is True means it can be renewed
                log(f"🔄 正在续费 ServerID: {k}")
                if renew(sessid, s, k, mailparser_id_list[i]):
                    log(f"🎉 ServerID: {k} 已成功续订!")
                else:
                    log(f"⚠️ ServerID: {k} 续订错误!")
            else:
                log(f"✅ ServerID: {k} 无需更新。")
        
        time.sleep(10) # 等待Euserv后台更新
        check(sessid, s)
        log("="*30)
        time.sleep(5)

    telegram()

if __name__ == "__main__":
     main_handler()
