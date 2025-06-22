# -*- coding: utf-8 -*-
# SPDX-License-Identifier: MIT
"""
nat.freecloud.ltd 自动签到脚本 (最终版 - Selenium)

功能:
- [最终方案] 使用undetected-chromedriver驱动一个真实的Chrome浏览器，完美绕过顶级Cloudflare防护。
- 使用 TrueCaptcha API 自动识别图形验证码。
- 从环境变量读取配置，适配青龙面板。
"""
import os
import base64
import html
import time
import requests      # 保留requests，用于请求不受保护的TrueCaptcha API
from urllib.parse import urljoin

# 引入Selenium相关库
import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

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
# 全局设置
# =====================================================================================
LOGIN_PAGE_URL = "https://nat.freecloud.ltd/login"
CHECKIN_URL = "https://nat.freecloud.ltd/user/checkin"
USER_PAGE_URL = "https://nat.freecloud.ltd/user"
DESP = ""

def log(info: str):
    emoji_map = {
        "开始处理": "🚀", "登录成功": "✅", "登录失败": "❌", "登录尝试": "🔑",
        "验证码识别": "🧩", "签到成功": "🎉", "已经签到": "😊", "签到失败": "⚠️",
        "任务结束": "🏁", "配置错误": "❗", "浏览器操作": "🌐"
    }
    for key, emoji in emoji_map.items():
        if key in info:
            info = f"{emoji} {info}"
            break
    print(info)
    global DESP
    DESP += info + "\n"

def solve_captcha_from_base64(b64_string: str) -> str:
    log("验证码识别: 正在提交API识别...")
    try:
        api_url = "https://api.apitruecaptcha.org/one/gettext"
        data = {"userid": TRUECAPTCHA_USERID, "apikey": TRUECAPTCHA_APIKEY, "data": b64_string, "case": "d", "len_min": "4", "len_max": "4"}
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

def main():
    log("任务开始: FreeCloud 自动签到 (Selenium模式)")
    if not all([FREECLOUD_USERNAME, FREECLOUD_PASSWORD, TRUECAPTCHA_USERID, TRUECAPTCHA_APIKEY]):
        log("配置错误: 网站用户名/密码或TrueCaptcha API信息不完整。")
        notify_telegram()
        return

    driver = None
    try:
        # --- 配置并启动浏览器 ---
        options = uc.ChromeOptions()
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')
        options.add_argument('--headless') # 使用无头模式，不在界面显示浏览器
        if PROXY_URL:
            options.add_argument(f'--proxy-server={PROXY_URL}')
        
        log("浏览器操作: 正在启动一个真实的Chrome浏览器...")
        driver = uc.Chrome(options=options)
        log("浏览器操作: 浏览器启动成功。")
        
        # --- 登录流程 ---
        log(f"浏览器操作: 正在导航到登录页面 {LOGIN_PAGE_URL}")
        driver.get(LOGIN_PAGE_URL)

        # 等待页面加载完成，特别是输入框出现
        wait = WebDriverWait(driver, 20)
        email_input = wait.until(EC.presence_of_element_located((By.ID, 'email')))
        
        log("浏览器操作: 页面加载完成，正在执行登录操作...")

        # 获取验证码图片的 base64 编码
        captcha_img = driver.find_element(By.TAG_NAME, 'img')
        # 有的网站验证码是JS生成的，直接用screenshot_as_base64最稳
        b64_string = captcha_img.screenshot_as_base64
        
        captcha_code = solve_captcha_from_base64(b64_string)
        if not captcha_code:
            raise Exception("无法识别验证码，任务失败。")

        # 输入账号、密码和验证码
        email_input.send_keys(FREECLOUD_USERNAME)
        driver.find_element(By.ID, 'password').send_keys(FREECLOUD_PASSWORD)
        driver.find_element(By.ID, 'captcha').send_keys(captcha_code)
        
        # 点击登录按钮
        driver.find_element(By.CSS_SELECTOR, 'button.btn.btn-primary').click()

        # 等待登录成功（判断URL是否跳转或特定元素出现）
        wait.until(EC.url_contains(USER_PAGE_URL))
        log("登录成功!")

        # --- 签到流程 ---
        log("浏览器操作: 正在执行签到...")
        # 直接用JS点击签到按钮，比模拟点击更稳定
        checkin_button = wait.until(EC.element_to_be_clickable((By.ID, 'checkin')))
        driver.execute_script("arguments[0].click();", checkin_button)
        
        # 等待签到结果（需要根据实际情况调整，例如等待一个提示框）
        time.sleep(5) # 等待一下让结果弹窗出来
        page_text = driver.page_source
        if "您似乎已经签到过了" in page_text or "签到成功" in page_text:
            log("签到成功: 或今天已经签到过了。")
        else:
            log("签到失败: 未检测到成功信息。")

    except Exception as e:
        log(f"任务失败: 发生严重错误: {e}")
    finally:
        if driver:
            driver.quit()
        log("任务结束")
        notify_telegram()

def notify_telegram():
    # ... (此函数无需修改) ...
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

if __name__ == "__main__":
    main()
