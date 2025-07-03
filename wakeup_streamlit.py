import requests
import time

# --- 请在这里修改成您的应用URL ---
APP_URL = "https://lovepeace.streamlit.app/"
# ---------------------------------

# 伪装成浏览器访问
headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/108.0.0.0 Safari/537.36',
    'Cache-Control': 'no-cache',
    'Pragma': 'no-cache'
}

print(f"开始唤醒应用: {APP_URL}")

try:
    # 发送GET请求，设置超时时间为30秒
    response = requests.get(APP_URL, headers=headers, timeout=30)
    
    # 检查HTTP状态码
    if response.status_code == 200:
        print(f"唤醒成功！状态码: {response.status_code}")
        # 因为您的应用有密码，返回的页面内容会是登录页，这是正常的
        # print(f"返回内容前50个字符: {response.text[:50]}")
    else:
        print(f"唤醒请求可能存在问题，状态码: {response.status_code}")
        
except requests.exceptions.RequestException as e:
    print(f"唤醒失败，发生错误: {e}")

print("任务执行完毕。")
