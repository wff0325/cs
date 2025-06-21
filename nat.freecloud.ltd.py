# -*- coding: utf-8 -*-
# SPDX-License-Identifier: MIT
"""
nat.freecloud.ltd 自动签到脚本 (青龙面板优化版)

功能:
- [终极方案] 使用 cloudscraper 库来专业地绕过 Cloudflare 安全拦截。
- 使用 TrueCaptcha API 自动识别图形和数学验证码
- 从环境变量读取配置，适配青龙面板
- 包含登录重试机制
- 格式化的日志输出
- 通过 Telegram Bot 发送通知
"""
import os
import re
import base64
import html
import cloudscraper  # <-- 使用 cloudscraper 替代 requests
from urllib.parse import urljoin

# =====================================================================================
# 环境变量配置 (无需变动)
# =====================================================================================
FREECLOUD_USERNAME = os.getenv('FREECLOUD_USERNAME')
FREECLOUD_PASSWORD = os.getenv('FREECLOUD_PASSWORD')
TRUECAPTCHA_USERID = os.getenv('TRUECAPTCHA_USERID')
TRUECAPTCHA_APIKEY = os.getenv('TRUECAPTCHA_APIKEY')
TG_BOT_TOKEN = os.getenv('TG_BOT_TOKEN')
TG_USER_ID = os.getenv('TG_USER_ID')
TG_API_HOST = os.getenv('TG_API_HOST', "https://api.telegram.org").rstrip('/')
PROXY_URL = os.getenv('PROXY_URL')
# cloudscraper 会自动处理代理，但我们需要将其格式化
PROXIES = {"http": PROXY_URL, "https": PROXY_URL} if PROXY_URL else None
# =====================================================================================


# =====================================================================================
# 全局设置 (无需变动)
# =====================================================================================
BASE_URL = "https://nat.freecloud.ltd"
LOGIN_URL = urljoin(BASE_URL, "/auth/login")
LOGIN_CAPTCHA_URL = urljoin(BASE_URL, "/captcha/default")
CHECKIN_URL = urljoin(BASE_URL, "/user/checkin")
USER_PAGE_URL = urljoin(BASE_URL, "/user")

FORM_FIELD_USERNAME = "email"
FORM_FIELD_PASSWORD = "passwd"
FORM_FIELD_LOGIN_CAPTCHA = "code"

LOGIN_MAX_RETRY_COUNT = 3
DESP = ""

def log(info: str):
    emoji_map = {
        "开始处理": "🚀", "登录成功": "✅", "登录失败": "❌", "登录尝试": "🔑",
        "验证码识别": "🧩", "签到成功": "🎉", "已经签到": "😊", "签到失败": "⚠️",
        "任务结束": "🏁", "配置错误": "❗", "网络错误": "🌐", "安全拦截": "🛡️"
    }
    for key, emoji in emoji_map.items():
        if key in info:
            info = f"{emoji} {info}"
            break
    print(info)
    global DESP
    DESP += info + "\n"

def solve_captcha(scraper: cloudscraper.CloudScraper, captcha_url: str) -> str:
    log("验证码识别: 正在请求 API...")
    if not TRUECAPTCHA_USERID or not TRUECAPTCHA_APIKEY:
        log("验证码识别: 未配置 TrueCaptcha API，无法继续。")
        return ""
    try:
        # 使用 scraper 对象进行请求
        response = scraper.get(captcha_url, stream=True, timeout=30)
        response.raise_for_status()
        encoded_string = base64.b64encode(response.content).decode('utf-8')
        
        api_url = "https://api.apitruecaptcha.org/one/gettext"
        data = {"userid": TRUECAPTCHA_USERID, "apikey": TRUECAPTCHA_APIKEY, "data": encoded_string, "case": "d", "len_min": "4", "len_max": "4"}
        
        # 请求验证码API时，使用普通的requests，因为它不需要过Cloudflare
        import requests
        r = requests.post(url=api_url, json=data, proxies=PROXIES, timeout=30)
        r.raise_for_status()
        
        result_json = r.json()
        if "result" in result_json:
            text = result_json["result"]
            log(f"验证码识别: API 返回 -> {text}")
            return text
        else:
            log(f"验证码识别: API 未返回有效结果: {result_json.get('status', '未知状态')}")
            return ""
    except Exception as e:
        log(f"验证码识别: 发生错误: {e}")
        return ""

def login(scraper: cloudscraper.CloudScraper, username: str, password: str) -> bool:
    for i in range(LOGIN_MAX_RETRY_COUNT):
        log(f"登录尝试: 第 {i + 1}/{LOGIN_MAX_RETRY_COUNT} 次...")
        try:
            # cloudscraper 会自动处理访问首页获取cookie和绕过JS盾的过程
            captcha_code = solve_captcha(scraper, LOGIN_CAPTCHA_URL)
            if not captcha_code:
                log("登录失败: 无法识别验证码，终止此次尝试。")
                continue
            
            login_data = {FORM_FIELD_USERNAME: username, FORM_FIELD_PASSWORD: password, FORM_FIELD_LOGIN_CAPTCHA: captcha_code, "remember_me": "on"}
            
            # 动态设置 Referer，更像浏览器
            scraper.headers.update({'Referer': LOGIN_URL})
            response = scraper.post(LOGIN_URL, data=login_data, timeout=30)
            response.raise_for_status()
            
            if USER_PAGE_URL in response.url or "我的卡片" in response.text or "邮箱" in response.text:
                log("登录成功!")
                return True
            else:
                log("登录失败: 可能是账号、密码或验证码错误。")
        except Exception as e:
            log(f"登录失败: 发生错误: {e}")
    return False

def check_in(scraper: cloudscraper.CloudScraper):
    try:
        log("开始执行签到流程...")
        # 动态设置 Referer
        scraper.headers.update({'Referer': USER_PAGE_URL})
        response = scraper.get(USER_PAGE_URL, timeout=30)
        response.raise_for_status()

        if "您似乎已经签到过了" in response.text or "明日再来" in response.text:
            log("已经签到: 今天已经签到过了，无需重复操作。")
            return

        checkin_response = scraper.post(CHECKIN_URL, timeout=30)
        checkin_response.raise_for_status()
        result_json = checkin_response.json()
        
        if result_json.get("ret") == 1:
            log(f"签到成功: {result_json.get('msg')}")
        else:
            log(f"签到失败: {result_json.get('msg', '未知错误')}")
    except Exception as e:
        log(f"签到失败: 发生错误: {e}")

def notify_telegram():
    if not TG_BOT_TOKEN or not TG_USER_ID: return
    safe_desp = html.escape(DESP)
    message = f"<b>FreeCloud 自动签到日志</b>\n\n<pre>{safe_desp}</pre>"
    data = {"chat_id": TG_USER_ID, "text": message, "parse_mode": "HTML", "disable_web_page_preview": "true"}
    try:
        import requests
        url = f"{TG_API_HOST}/bot{TG_BOT_TOKEN}/sendMessage"
        response = requests.post(url, data=data, proxies=PROXIES, timeout=30)
        if response.status_code == 200:
            print("Telegram Bot 推送成功")
        else:
            print(f"Telegram Bot 推送失败: Status Code: {response.status_code}, Response: {response.text}")
    except Exception as e:
        print(f"Telegram Bot 推送异常: {e}")

def main():
    log("任务开始: FreeCloud 自动签到")
    if not all([FREECLOUD_USERNAME, FREECLOUD_PASSWORD, TRUECAPTCHA_USERID, TRUECAPTCHA_APIKEY]):
        log("配置错误: 网站用户名/密码或TrueCaptcha API信息不完整，请检查环境变量。")
        notify_telegram()
        return

    # 创建一个 scraper 实例，它可以像 requests.Session 一样使用
    scraper = cloudscraper.create_scraper()
    # 如果设置了代理，则应用到 scraper
    if PROXIES:
        scraper.proxies.update(PROXIES)

    if login(scraper, FREECLOUD_USERNAME, FREECLOUD_PASSWORD):
        check_in(scraper)
    else:
        log("任务结束: 因登录失败或被拦截，未执行签到。")
    
    log("任务结束")
    notify_telegram()

if __name__ == "__main__":
    main()
