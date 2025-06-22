# -*- coding: utf-8 -*-
# SPDX-License-Identifier: MIT
"""
nat.freecloud.ltd 自动签到脚本 (青龙面板优化版)

功能:
- [正确路径版] 根据用户发现的正确登录路径(/login)进行修正，完美模拟真实用户操作流程。
- 使用 cloudscraper 库绕过 Cloudflare 安全拦截。
- 使用 TrueCaptcha API 自动识别图形验证码。
- 从环境变量读取配置，适配青龙面板。
"""
import os
import base64
import html
import cloudscraper  # 使用 cloudscraper 替代 requests
import requests      # 保留一个普通的requests，用于请求不受保护的TrueCaptcha API
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
PROXIES = {"http": PROXY_URL, "https": PROXY_URL} if PROXY_URL else None
# =====================================================================================


# =====================================================================================
# 全局设置 (已根据新发现修正)
# =====================================================================================
BASE_URL = "https://nat.freecloud.ltd"
# [重大更新] 区分了用户访问的页面地址和表单提交的API地址
LOGIN_PAGE_URL = urljoin(BASE_URL, "/login")          # 用户浏览器访问的登录页面
LOGIN_POST_URL = urljoin(BASE_URL, "/auth/login")      # 登录表单提交的目标地址
LOGIN_CAPTCHA_URL = urljoin(BASE_URL, "/captcha/default") # 验证码图片地址
CHECKIN_URL = urljoin(BASE_URL, "/user/checkin")         # 签到提交地址
USER_PAGE_URL = urljoin(BASE_URL, "/user")              # 用户中心地址

FORM_FIELD_USERNAME = "email"
FORM_FIELD_PASSWORD = "passwd"
FORM_FIELD_LOGIN_CAPTCHA = "code"

LOGIN_MAX_RETRY_COUNT = 3
DESP = ""

def log(info: str):
    emoji_map = {
        "开始处理": "🚀", "登录成功": "✅", "登录失败": "❌", "登录尝试": "🔑",
        "验证码识别": "🧩", "签到成功": "🎉", "已经签到": "😊", "签到失败": "⚠️",
        "任务结束": "🏁", "配置错误": "❗", "网络错误": "🌐", "路径正确": "➡️"
    }
    for key, emoji in emoji_map.items():
        if key in info:
            info = f"{emoji} {info}"
            break
    print(info)
    global DESP
    DESP += info + "\n"

def solve_captcha(scraper: cloudscraper.CloudScraper) -> str:
    log("验证码识别: 正在获取验证码图片...")
    try:
        response = scraper.get(LOGIN_CAPTCHA_URL, stream=True, timeout=30)
        response.raise_for_status()
        log("验证码识别: 图片获取成功，正在提交API识别...")
        
        encoded_string = base64.b64encode(response.content).decode('utf-8')
        api_url = "https://api.apitruecaptcha.org/one/gettext"
        data = {"userid": TRUECAPTCHA_USERID, "apikey": TRUECAPTCHA_APIKEY, "data": encoded_string, "case": "d", "len_min": "4", "len_max": "4"}
        
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
            # [核心修正] 访问正确的、公开的登录页面
            log(f"路径正确: 正在访问公开登录页面 {LOGIN_PAGE_URL} ...")
            scraper.get(LOGIN_PAGE_URL, timeout=30).raise_for_status()
            log("页面访问成功，Cloudflare验证已通过。")

            # 在已建立的合法会话中请求验证码
            captcha_code = solve_captcha(scraper)
            if not captcha_code:
                log("登录失败: 无法识别验证码，终止此次尝试。")
                continue
            
            login_data = {FORM_FIELD_USERNAME: username, FORM_FIELD_PASSWORD: password, FORM_FIELD_LOGIN_CAPTCHA: captcha_code, "remember_me": "on"}
            
            # [核心修正] 将数据提交到正确的处理地址
            log(f"路径正确: 正在向 {LOGIN_POST_URL} 提交登录数据...")
            response = scraper.post(LOGIN_POST_URL, data=login_data, timeout=30)
            response.raise_for_status()
            
            if USER_PAGE_URL in response.url or "我的卡片" in response.text or "邮箱" in response.text:
                log("登录成功!")
                return True
            else:
                log("登录失败: 可能是账号、密码或验证码错误。")
        except Exception as e:
            log(f"登录失败: 发生严重错误: {e}")
    return False

def check_in(scraper: cloudscraper.CloudScraper):
    try:
        log("开始执行签到流程...")
        scraper.get(USER_PAGE_URL, timeout=30).raise_for_status()
        
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

    scraper = cloudscraper.create_scraper(
        browser={'browser': 'chrome', 'platform': 'windows', 'mobile': False}
    )
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
