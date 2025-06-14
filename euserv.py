# SPDX-License-Identifier: GPL-3.0-or-later

"""
euserv 自动续期脚本 (青龙面板优化版)
功能:
* 使用 TrueCaptcha API 自动识别验证码
* 发送通知到 Telegram
* 增加登录失败重试机制
* 日志信息格式化
* 从环境变量读取配置，适配青龙面板
"""

import re
import json
import time
import base64
import requests
import os
from bs4 import BeautifulSoup

# =====================================================================================
# 读取环境变量中的配置，如果环境变量不存在，则使用冒号后的默认值（建议在青龙面板配置环境变量）
# =====================================================================================

# 账户信息：用户名和密码 (多个账号请用空格隔开)
# 青龙环境变量名称: EUSERV_USERNAME
USERNAME = os.getenv('EUSERV_USERNAME', '改为你的EUserV客户ID 或 邮箱')
# 青龙环境变量名称: EUSERV_PASSWORD
PASSWORD = os.getenv('EUSERV_PASSWORD', '改为你的EUserV的密码')

# TrueCaptcha API 配置 (申请地址: https://truecaptcha.org/)
# 青龙环境变量名称: TRUECAPTCHA_USERID
TRUECAPTCHA_USERID = os.getenv('TRUECAPTCHA_USERID', '改为你的TrueCaptcha UserID')
# 青龙环境变量名称: TRUECAPTCHA_APIKEY
TRUECAPTCHA_APIKEY = os.getenv('TRUECAPTCHA_APIKEY', '改为你的TrueCaptcha APIKEY')

# Mailparser 配置 (多个ID请用空格隔开, 顺序必须与账号对应)
# 青龙环境变量名称: MAILPARSER_DOWNLOAD_URL_ID
MAILPARSER_DOWNLOAD_URL_ID = os.getenv('MAILPARSER_DOWNLOAD_URL_ID', '改为你的Mailparser下载URL的最后几位')
MAILPARSER_DOWNLOAD_BASE_URL = "https://files.mailparser.io/d/" # 无需更改除非你要反代

# Telegram Bot 推送配置
# 青龙环境变量名称: TG_BOT_TOKEN
TG_BOT_TOKEN = os.getenv('TG_BOT_TOKEN', "改为你的Telegram机器人Token")
# 青龙环境变量名称: TG_USER_ID
TG_USER_ID = os.getenv('TG_USER_ID', "改为你的用户ID")
# 青龙环境变量名称: TG_API_HOST (可选, 用于反代Telegram API)
TG_API_HOST = os.getenv('TG_API_HOST', "https://api.telegram.org")

# 代理设置 (如果需要)
# 青龙环境变量名称: PROXY_URL, 例如: http://127.0.0.1:10808
proxy_url = os.getenv('PROXY_URL')
PROXIES = {"http": proxy_url, "https": proxy_url} if proxy_url else None

# =====================================================================================
# 以下为脚本核心代码，通常无需修改
# =====================================================================================

# 最大登录重试次数
LOGIN_MAX_RETRY_COUNT = 5
# 接收 PIN 的等待时间，单位为秒
WAITING_TIME_OF_PIN = 15
# 是否检查验证码解决器的使用情况
CHECK_CAPTCHA_SOLVER_USAGE = True

user_agent = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/95.0.4638.69 Safari/537.36"
)

desp = ""  # 日志信息

def log(info: str):
    # 打印并记录日志信息，附带 emoji 以增加可读性
    emoji_map = {
        "正在续费": "🔄", "检测到": "🔍", "ServerID": "🔗", "无需更新": "✅",
        "续订错误": "⚠️", "已成功续订": "🎉", "所有工作完成": "🏁", "登陆失败": "❗",
        "验证通过": "✔️", "验证失败": "❌", "API 使用次数": "📊", "验证码是": "🔢",
        "登录尝试": "🔑", "[MailParser]": "📧", "[Captcha Solver]": "🧩", "[AutoEUServerless]": "🌐",
    }
    # 对每个关键字进行检查，并在找到时添加 emoji
    for key, emoji in emoji_map.items():
        if key in info:
            info = emoji + " " + info
            break

    print(info)
    global desp
    desp += info + "\n\n"

# 登录重试装饰器
def login_retry(*args, **kwargs):
    def wrapper(func):
        def inner(username, password):
            ret, ret_session = func(username, password)
            max_retry = kwargs.get("max_retry")
            # 默认重试 3 次
            if not max_retry:
                max_retry = 3
            number = 0
            if ret == "-1":
                while number < max_retry:
                    number += 1
                    if number > 1:
                        log("[AutoEUServerless] 登录尝试第 {} 次".format(number))
                    sess_id, session = func(username, password)
                    if sess_id != "-1":
                        return sess_id, session
                    else:
                        if number == max_retry:
                            return sess_id, session
            else:
                return ret, ret_session
        return inner
    return wrapper

# 验证码解决器
def captcha_solver(captcha_image_url: str, session: requests.session) -> dict:
    # TrueCaptcha API 文档: https://apitruecaptcha.org/api
    response = session.get(captcha_image_url, proxies=PROXIES)
    encoded_string = base64.b64encode(response.content)
    url = "https://api.apitruecaptcha.org/one/gettext"

    data = {
        "userid": TRUECAPTCHA_USERID, "apikey": TRUECAPTCHA_APIKEY, "case": "mixed",
        "mode": "human", "data": str(encoded_string)[2:-1],
    }
    r = requests.post(url=url, json=data, proxies=PROXIES)
    j = json.loads(r.text)
    return j

# 处理验证码解决结果
def handle_captcha_solved_result(solved: dict) -> str:
    if "result" in solved:
        solved_text = solved["result"]
        if "RESULT  IS" in solved_text:
            log("[Captcha Solver] 使用的是演示 apikey。")
            text = re.findall(r"RESULT  IS . (.*) .", solved_text)[0]
        else:
            log("[Captcha Solver] 使用的是您自己的 apikey。")
            text = solved_text
        operators = ["X", "x", "+", "-"]
        if any(x in text for x in operators):
            for operator in operators:
                operator_pos = text.find(operator)
                op_symbol = operator
                if operator == "x" or operator == "X":
                    op_symbol = "*"
                if operator_pos != -1:
                    left_part = text[:operator_pos].strip()
                    right_part = text[operator_pos + 1 :].strip()
                    if left_part.isdigit() and right_part.isdigit():
                        return str(eval(f"{left_part} {op_symbol} {right_part}"))
                    else:
                        return text
        else:
            return text
    else:
        print(solved)
        raise KeyError("未找到解析结果。")

# 获取验证码解决器使用情况
def get_captcha_solver_usage() -> dict:
    url = "https://api.apitruecaptcha.org/one/getusage"
    params = { "username": TRUECAPTCHA_USERID, "apikey": TRUECAPTCHA_APIKEY }
    r = requests.get(url=url, params=params, proxies=PROXIES)
    j = json.loads(r.text)
    return j

# 从 Mailparser 获取 PIN
def get_pin_from_mailparser(url_id: str) -> str:
    response = requests.get(f"{MAILPARSER_DOWNLOAD_BASE_URL}{url_id}", proxies=PROXIES)
    pin = response.json()[0]["pin"]
    return pin

# 登录函数
@login_retry(max_retry=LOGIN_MAX_RETRY_COUNT)
def login(username: str, password: str) -> (str, requests.session):
    headers = {"user-agent": user_agent, "origin": "https://www.euserv.com"}
    url = "https://support.euserv.com/index.iphp"
    captcha_image_url = "https://support.euserv.com/securimage_show.php"
    session = requests.Session()

    sess = session.get(url, headers=headers, proxies=PROXIES)
    sess_id = re.findall("PHPSESSID=(\\w{10,100});", str(sess.headers))[0]
    session.get("https://support.euserv.com/pic/logo_small.png", headers=headers, proxies=PROXIES)

    login_data = {
        "email": username, "password": password, "form_selected_language": "en",
        "Submit": "Login", "subaction": "login", "sess_id": sess_id,
    }
    f = session.post(url, headers=headers, data=login_data, proxies=PROXIES)
    f.raise_for_status()

    if "Hello" not in f.text and "Confirm or change your customer data here" not in f.text:
        if "To finish the login process please solve the following captcha." not in f.text:
            return "-1", session
        else:
            log("[Captcha Solver] 正在进行验证码识别...")
            solved_result = captcha_solver(captcha_image_url, session)
            captcha_code = handle_captcha_solved_result(solved_result)
            log(f"[Captcha Solver] 识别的验证码是: {captcha_code}")

            if CHECK_CAPTCHA_SOLVER_USAGE and "demo" not in TRUECAPTCHA_APIKEY:
                try:
                    usage = get_captcha_solver_usage()
                    log(f"[Captcha Solver] 当前日期 {usage[0]['date']} API 使用次数: {usage[0]['count']}")
                except Exception as e:
                    log(f"[Captcha Solver] 查询API用量失败: {e}")

            f2 = session.post(
                url, headers=headers, proxies=PROXIES,
                data={ "subaction": "login", "sess_id": sess_id, "captcha_code": captcha_code, }
            )
            if "To finish the login process please solve the following captcha." not in f2.text:
                log("[Captcha Solver] 验证通过")
                return sess_id, session
            else:
                log("[Captcha Solver] 验证失败")
                return "-1", session
    else:
        return sess_id, session

# 获取服务器列表
def get_servers(sess_id: str, session: requests.session) -> {}:
    d = {}
    url = f"https://support.euserv.com/index.iphp?sess_id={sess_id}"
    headers = {"user-agent": user_agent, "origin": "https://www.euserv.com"}
    f = session.get(url=url, headers=headers, proxies=PROXIES)
    f.raise_for_status()
    soup = BeautifulSoup(f.text, "html.parser")
    for tr in soup.select("#kc2_order_customer_orders_tab_content_1 .kc2_order_table.kc2_content_table tr"):
        server_id_tag = tr.select(".td-z1-sp1-kc")
        if not len(server_id_tag) == 1:
            continue
        server_id = server_id_tag[0].get_text(strip=True)
        if not server_id:
            continue
        
        action_container = tr.select_one(".td-z1-sp2-kc .kc2_order_action_container")
        is_renewable = "Contract extension possible from" not in action_container.get_text()
        d[server_id] = is_renewable
    return d

# 续期操作
def renew(sess_id: str, session: requests.session, order_id: str, mailparser_dl_url_id: str) -> bool:
    url = "https://support.euserv.com/index.iphp"
    headers = {
        "user-agent": user_agent, "Host": "support.euserv.com",
        "origin": "https://support.euserv.com", "Referer": "https://support.euserv.com/index.iphp",
    }
    data = {
        "Submit": "Extend contract", "sess_id": sess_id, "ord_no": order_id,
        "subaction": "choose_order", "choose_order_subaction": "show_contract_details",
    }
    session.post(url, headers=headers, data=data, proxies=PROXIES)

    session.post(
        url, headers=headers, proxies=PROXIES,
        data={
            "sess_id": sess_id, "subaction": "show_kc2_security_password_dialog",
            "prefix": "kc2_customer_contract_details_extend_contract_", "type": "1",
        },
    )

    log(f"[MailParser] 等待 {WAITING_TIME_OF_PIN} 秒以接收 PIN 码邮件...")
    time.sleep(WAITING_TIME_OF_PIN)
    pin = get_pin_from_mailparser(mailparser_dl_url_id)
    log(f"[MailParser] 获取到的 PIN: {pin}")

    data_pin = {
        "auth": pin, "sess_id": sess_id, "subaction": "kc2_security_password_get_token",
        "prefix": "kc2_customer_contract_details_extend_contract_", "type": "1",
        "ident": f"kc2_customer_contract_details_extend_contract_{order_id}",
    }
    f = session.post(url, headers=headers, data=data_pin, proxies=PROXIES)
    f.raise_for_status()
    response_json = f.json()
    if response_json.get("rs") != "success":
        log(f"[AutoEUServerless] PIN 验证失败: {response_json.get('msg')}")
        return False
    token = response_json["token"]["value"]
    
    data_renew = {
        "sess_id": sess_id, "ord_id": order_id,
        "subaction": "kc2_customer_contract_details_extend_contract_term", "token": token,
    }
    session.post(url, headers=headers, data=data_renew, proxies=PROXIES)
    time.sleep(5)
    return True

# 检查续期状态
def check(sess_id: str, session: requests.session):
    log("[AutoEUServerless] 正在检查续期后的状态...")
    d = get_servers(sess_id, session)
    all_ok = True
    for key, val in d.items():
        if val:
            all_ok = False
            log(f"[AutoEUServerless] ServerID: {key} 续期后检查发现仍可续期，可能失败了!")
    if all_ok:
        log("[AutoEUServerless] 所有工作完成！尽情享受~")

# 发送 Telegram 通知
def telegram():
    # ==================== FIX STARTS HERE (V2) ====================
    # 正确地将特殊字符转义为其HTML实体，以防止解析错误
    safe_desp = desp.replace("&", "&").replace("<", "<").replace(">", ">")
    # ====================  FIX ENDS HERE (V2)  ====================

    message = (
        "<b>AutoEUServerless 日志</b>\n\n" + safe_desp + # 使用转义后的安全日志内容
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
    # 请不要删除本段版权声明, 开发不易, 感谢! 感谢!
    # 请勿二次售卖,出售,开源不易,万分感谢!
    data = {
        "chat_id": TG_USER_ID, "text": message,
        "parse_mode": "HTML", "disable_web_page_preview": "true"
    }
    try:
        response = requests.post(
            f"{TG_API_HOST}/bot{TG_BOT_TOKEN}/sendMessage", data=data, proxies=PROXIES, timeout=10
        )
        if response.status_code == 200:
            print("Telegram Bot 推送成功")
        else:
            print(f"Telegram Bot 推送失败: {response.text}")
    except Exception as e:
        print(f"Telegram Bot 推送异常: {e}")

def main():
    if not all([USERNAME, PASSWORD, TRUECAPTCHA_USERID, TRUECAPTCHA_APIKEY, MAILPARSER_DOWNLOAD_URL_ID]):
        log("[AutoEUServerless] 必要配置不完整，请检查环境变量设置！")
        if TG_BOT_TOKEN and TG_USER_ID:
            telegram()
        exit(1)
        
    user_list = USERNAME.strip().split()
    passwd_list = PASSWORD.strip().split()
    mailparser_dl_url_id_list = MAILPARSER_DOWNLOAD_URL_ID.strip().split()
    
    if not (len(user_list) == len(passwd_list) == len(mailparser_dl_url_id_list)):
        log("[AutoEUServerless] 账号、密码、Mailparser ID 数量不匹配! 请用空格分隔多个值。")
        if TG_BOT_TOKEN and TG_USER_ID:
            telegram()
        exit(1)

    for i in range(len(user_list)):
        print("*" * 40)
        log(f"[AutoEUServerless] ===> 开始处理第 {i + 1}/{len(user_list)} 个账号: {user_list[i]} <===")
        sessid, s = login(user_list[i], passwd_list[i])
        if sessid == "-1":
            log(f"[AutoEUServerless] 第 {i + 1} 个账号登陆失败，请检查登录信息或网络")
            continue
        
        log(f"[AutoEUServerless] 账号 {user_list[i]} 登录成功")
        servers = get_servers(sessid, s)
        log(f"[AutoEUServerless] 检测到账号下有 {len(servers)} 台 VPS，正在尝试续期")
        
        if not servers:
            log("[AutoEUServerless] 未找到任何 VPS，跳过续期。")
            continue

        for server_id, can_renew in servers.items():
            if can_renew:
                log(f"[AutoEUServerless] ServerID: {server_id} 正在续费...")
                if not renew(sessid, s, server_id, mailparser_dl_url_id_list[i]):
                    log(f"[AutoEUServerless] ServerID: {server_id} 续订错误!")
                else:
                    log(f"[AutoEUServerless] ServerID: {server_id} 已成功续订!")
            else:
                log(f"[AutoEUServerless] ServerID: {server_id} 无需更新")
        
        time.sleep(15)
        check(sessid, s)
        time.sleep(5)
    
    # 发送 Telegram 通知
    if TG_BOT_TOKEN and TG_USER_ID:
        telegram()
    print("*" * 40)
    log("所有账号处理完毕。")

if __name__ == "__main__":
     main()
