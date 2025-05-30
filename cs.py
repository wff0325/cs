import requests
import time
from datetime import datetime

# --- 配置 ---
URLS_TO_CHECK = [
    "https://liii.zabc.net",
    "https://dingyue.zabc.net",
    "https://llli.zabc.net",
    "https://lljj.zabc.net",
    "https://sasa.zabc.net"
]
# 也可以加上之前能成功的URL进行对比
# URLS_TO_CHECK.extend([
#     "https://fl.opb.dpdns.org/65abc702-dde4-4e84-8244-e79273981297",
#     "https://am.opb.dpdns.org/f8ff1eb2-97c1-4469-ebe1-8f13293ddcb6"
# ])

TIMEOUT_SECONDS = 10  # 每个请求的超时时间（秒）
INTERVAL_SECONDS = 300 # 每次检查之间的间隔时间（秒），例如 300秒 = 5分钟
# --- 配置结束 ---

def check_url(url):
    """访问单个URL并打印结果"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    try:
        # 发送GET请求，设置超时
        # allow_redirects=True 是默认行为，可以明确写出
        # verify=True 是默认行为，进行SSL证书验证，如果目标站点证书有问题且你想忽略，可以设为 False (不推荐)
        response = requests.get(url, timeout=TIMEOUT_SECONDS, allow_redirects=True, verify=True)

        if response.ok: # 状态码在 200-299 之间
            print(f"✅ [{timestamp}] 成功: {url} (状态: {response.status_code})")
        else:
            print(f"⚠️ [{timestamp}] 注意: {url} (状态: {response.status_code} - {response.reason})")

    except requests.exceptions.Timeout:
        print(f"⌛️ [{timestamp}] 超时: {url} (超过 {TIMEOUT_SECONDS} 秒)")
    except requests.exceptions.ConnectionError as e:
        # ConnectionError 是一个更广泛的错误，ETIMEDOUT 是其一种具体表现
        # 我们可以尝试获取更底层的错误信息，但requests库可能已经将其包装
        # str(e) 通常会包含一些有用的信息
        print(f"❌ [{timestamp}] 连接失败: {url}, 错误: {str(e)}")
    except requests.exceptions.RequestException as e:
        # 捕获其他所有requests库可能抛出的异常
        print(f"❌ [{timestamp}] 请求错误: {url}, 错误: {str(e)}")
    except Exception as e:
        # 捕获意料之外的任何其他错误
        print(f"💥 [{timestamp}] 未知错误: {url}, 错误: {str(e)}")

def main_loop():
    """主循环，定时检查所有URL"""
    print(f"🚀 定时访问任务启动，每隔 {INTERVAL_SECONDS} 秒检查 {len(URLS_TO_CHECK)} 个URL。")
    print(f"   URL列表: {', '.join(URLS_TO_CHECK)}")
    print(f"   单次请求超时: {TIMEOUT_SECONDS} 秒")
    print("-" * 30)

    while True:
        print(f"\n--- 开始新一轮检查 ({datetime.now().strftime('%Y-%m-%d %H:%M:%S')}) ---")
        for url in URLS_TO_CHECK:
            check_url(url)
            time.sleep(0.5) # 在检查每个URL之间稍微停顿一下，避免过于频繁

        print(f"--- 本轮检查结束，等待 {INTERVAL_SECONDS} 秒后进行下一轮 ---")
        time.sleep(INTERVAL_SECONDS)

if __name__ == "__main__":
    try:
        main_loop()
    except KeyboardInterrupt:
        print("\n🚫 任务被用户手动中断。")
    except Exception as e:
        print(f"💥 主程序发生严重错误: {e}")
