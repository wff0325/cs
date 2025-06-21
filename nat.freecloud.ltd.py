# -*- coding: utf-8 -*-
# SPDX-License-Identifier: MIT
"""
nat.freecloud.ltd 自动签到脚本 (青龙面板优化版)

功能:
- 使用 TrueCaptcha API 自动识别图形和数学验证码
- 从环境变量读取配置，适配青龙面板
- 包含登录重试机制
- 格式化的日志输出
- 通过 Telegram Bot 发送通知 (支持API反代)
- 支持全局网络代理
"""
import os
import re
import base64
import requests
import html
from urllib.parse import urljoin
from bs4 import BeautifulSoup

# =====================================================================================
# 环境变量配置 (请在青龙面板的环境变量设置中添加)
# =====================================================================================
# -- 网站凭据 (必需) --
FREECLOUD_USERNAME = os.getenv('FREECLOUD_USERNAME')
FREECLOUD_PASSWORD = os.getenv('FREECLOUD_PASSWORD')

# -- TrueCaptcha API (必需) --
TRUECAPTCHA_USERID = os.getenv('TRUECAPTCHA_USERID')
TRUECAPTCHA_APIKEY = os.getenv('TRUECAPTCHA_APIKEY')

# -- Telegram Bot 通知 (可选) --
TG_BOT_TOKEN = os.getenv('TG_BOT_TOKEN')
TG_USER_ID = os.getenv('TG_USER_ID')
TG_API_HOST = os.getenv('TG_API_HOST', "https://api.telegram.org").rstrip('/')

# -- 网络代理 (可选, 如果服务器访问外网困难) --
PROXY_URL = os.getenv('PROXY_URL')
PROXIES = {"http": PROXY_URL, "https": PROXY_URL} if PROXY_URL else None
# =====================================================================================


# =====================================================================================
# 全局设置 (通常无需修改，但如果网站更新，可能需要抓包调整此处)
# =====================================================================================
BASE_URL = "https://nat.freecloud.ltd"
LOGIN_URL = urljoin(BASE_URL, "/auth/login")
LOGIN_CAPTCHA_URL = urljoin(BASE_URL, "/captcha/default")
CHECKIN_URL = urljoin(BASE_URL, "/user/checkin")
USER_PAGE_URL = urljoin(BASE_URL, "/user")

# 表单字段名 (根据浏览器开发者工具抓包确认)
FORM_FIELD_USERNAME = "email"
FORM_FIELD_PASSWORD = "passwd"
FORM_FIELD_LOGIN_CAPTCHA = "code"

LOGIN_MAX_RETRY_COUNT = 3
USER_AGENT = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
              "Chrome/108.0.0.0 Safari/537.36")
HEADERS = {"User-Agent": USER_AGENT, "Origin": BASE_URL}
DESP = "" # 用于存储日志，最后发送通知

def log(info: str):
    """格式化日志输出，并记录到全局日志变量"""
    emoji_map = {
        "开始处理": "🚀", "登录成功": "✅", "登录失败": "❌", "登录尝试": "🔑",
        "验证码识别": "🧩", "签到成功": "🎉", "已经签到": "😊", "签到失败": "⚠️",
        "任务结束": "🏁", "配置错误": "❗", "网络错误": "🌐",
    }
    for key, emoji in emoji_map.items():
        if key in info:
            info = f"{emoji} {info}"
            break
    print(info)
    global DESP
    DESP += info + "\n"

def solve_captcha(session: requests.Session, captcha_url: str, is_math: bool = False) -> str:
    """调用 TrueCaptcha API 识别验证码，并处理数学运算"""
    log("验证码识别: 正在请求 API...")
    if not TRUECAPTCHA_USERID or not TRUECAPTCHA_APIKEY:
        log("验证码识别: 未配置 TrueCaptcha API，无法继续。")
        return ""

    try:
        response = session.get(captcha_url, headers=HEADERS, proxies=PROXIES, stream=True)
        response.raise_for_status()
        encoded_string = base64.b64encode(response.content).decode('utf-8')

        api_url = "https://api.apitruecaptcha.org/one/gettext"
        data = {"userid": TRUECAPTCHA_USERID, "apikey": TRUECAPTCHA_APIKEY, "data": encoded_string}
        
        if not is_math:
            # 登录验证码为4位数字
            data.update({"case": "d", "len_min": "4", "len_max": "4"})

        r = requests.post(url=api_url, json=data, proxies=PROXIES, timeout=20)
        r.raise_for_status()
        result_json = r.json()

        if "result" in result_json:
            text = result_json["result"]
            log(f"验证码识别: API 返回 -> {text}")
            
            if is_math:
                # 清理表达式: 替换符号, 移除等号及多余字符
                cleaned_text = text.replace('x', '*').replace('X', '*').replace('÷', '/').strip()
                cleaned_text = re.split(r'[=\s]', cleaned_text)[0]
                try:
                    math_result = str(eval(cleaned_text))
                    log(f"验证码识别: 数学题计算结果 -> {math_result}")
                    return math_result
                except Exception as e:
                    log(f"验证码识别: 数学题计算失败: {e}")
                    return ""
            return text
        else:
            log(f"验证码识别: API 未返回有效结果: {result_json.get('status', '未知状态')}")
            return ""

    except Exception as e:
        log(f"验证码识别: 发生错误: {e}")
        return ""

def login(session: requests.Session, username: str, password: str) -> bool:
    """处理登录流程，包含重试机制"""
    for i in range(LOGIN_MAX_RETRY_COUNT):
        log(f"登录尝试: 第 {i + 1}/{LOGIN_MAX_RETRY_COUNT} 次...")
        try:
            session.get(LOGIN_URL, headers=HEADERS, proxies=PROXIES) # 获取cookie
            captcha_code = solve_captcha(session, LOGIN_CAPTCHA_URL)
            if not captcha_code:
                log("登录失败: 无法识别验证码，终止此次尝试。")
                continue

            login_data = {
                FORM_FIELD_USERNAME: username,
                FORM_FIELD_PASSWORD: password,
                FORM_FIELD_LOGIN_CAPTCHA: captcha_code,
                "remember_me": "on",
            }
            response = session.post(LOGIN_URL, headers=HEADERS, data=login_data, proxies=PROXIES)
            response.raise_for_status()

            if USER_PAGE_URL in response.url or "我的卡片" in response.text:
                log("登录成功!")
                return True
            else:
                log("登录失败: 可能是账号、密码或验证码错误。")

        except requests.exceptions.RequestException as e:
            log(f"登录失败: 发生网络错误: {e}")
            
    return False

def check_in(session: requests.Session):
    """处理签到流程"""
    try:
        log("开始执行签到流程...")
        response = session.get(USER_PAGE_URL, headers=HEADERS, proxies=PROXIES)
        response.raise_for_status()

        if "您似乎已经签到过了" in response.text or "明日再来" in response.text:
            log("已经签到: 今天已经签到过了，无需重复操作。")
            return

        # 网站在签到时会直接将结果嵌入到POST请求的JSON中，无需再次识别
        # 但如果未来需要，可以使用BeautifulSoup解析页面寻找验证码
        # soup = BeautifulSoup(response.text, 'html.parser')
        # ...

        checkin_response = session.post(CHECKIN_URL, headers=HEADERS, proxies=PROXIES)
        checkin_response.raise_for_status()
        result_json = checkin_response.json()
        
        if result_json.get("ret") == 1:
            log(f"签到成功: {result_json.get('msg')}")
        else:
            log(f"签到失败: {result_json.get('msg', '未知错误')}")
            
    except requests.exceptions.RequestException as e:
        log(f"签到失败: 发生网络错误: {e}")
    except Exception as e:
        log(f"签到失败: 发生未知错误: {e}")

def notify_telegram():
    """通过 Telegram Bot 发送通知"""
    if not TG_BOT_TOKEN or not TG_USER_ID:
        return

    safe_desp = html.escape(DESP)
    message = f"<b>FreeCloud 自动签到日志</b>\n\n<pre>{safe_desp}</pre>"
    
    data = {
        "chat_id": TG_USER_ID,
        "text": message,
        "parse_mode": "HTML",
        "disable_web_page_preview": "true"
    }
    try:
        # 使用包含 TG_API_HOST 的完整 URL
        url = f"{TG_API_HOST}/bot{TG_BOT_TOKEN}/sendMessage"
        response = requests.post(url, data=data, proxies=PROXIES, timeout=10)
        if response.status_code == 200:
            print("Telegram Bot 推送成功")
        else:
            print(f"Telegram Bot 推送失败: Status Code: {response.status_code}, Response: {response.text}")
    except Exception as e:
        print(f"Telegram Bot 推送异常: {e}")

def main():
    """主函数"""
    log("任务开始: FreeCloud 自动签到")
    if not all([FREECLOUD_USERNAME, FREECLOUD_PASSWORD, TRUECAPTCHA_USERID, TRUECAPTCHA_APIKEY]):
        log("配置错误: 网站用户名/密码或TrueCaptcha API信息不完整，请检查环境变量。")
        notify_telegram()
        return

    with requests.Session() as session:
        if login(session, FREECLOUD_USERNAME, FREECLOUD_PASSWORD):
            check_in(session)
        else:
            log("任务结束: 因登录失败，未执行签到。")
    
    log("任务结束")
    notify_telegram()

if __name__ == "__main__":
    main()
