// 建议将此行放在脚本顶部
const KEEPALIVE_URLS_ENV = process.env.KEEPALIVE_URLS; // 从环境变量读取URL列表

// 你可以修改这里的默认URL，或者通过环境变量 KEEPALIVE_URLS 来配置
const defaultUrlString = 'https://fl.opb.dpdns.org/65abc702-dde4-4e84-8244-e79273981297,https://am.opb.dpdns.org/f8ff1eb2-97c1-4469-ebe1-8f13293ddcb6,https://lljj.zabc.net/7c1bf604-fe15-4509-862c-93cdb5e33380';
const urlString = KEEPALIVE_URLS_ENV || defaultUrlString;

const urls = urlString
  .split(/[\s,，]+/) // 使用正则表达式分割，支持空格、英文逗号、中文逗号
  .map(url => url.trim()) // 去除每个URL两端的空白字符
  .filter(url => url && (url.startsWith('http://') || url.startsWith('https://'))); // 确保URL不为空且以 http(s):// 开头

const TIMEOUT = 5000; // 5 秒超时

// Node.js v18+ 版本全局自带 fetch 和 AbortController。
// 如果你的 Node.js 版本较低，可能需要安装 'node-fetch' 并导入。
// 例如: // const fetch = (await import('node-fetch')).default;
// 青龙面板通常运行较新的 Node.js 版本。

async function fetchWithTimeout(url) {
  const controller = new AbortController();
  const timeoutId = setTimeout(() => {
    controller.abort();
    // console.log(`DEBUG: Abort triggered for ${url}`); // 可选的调试日志
  }, TIMEOUT);

  try {
    // console.log(`DEBUG: Fetching ${url}`); // 可选的调试日志
    const response = await fetch(url, {
      signal: controller.signal,
      // 可以添加更多 fetch 选项，例如 headers, method 等，如果需要的话
      // headers: { 'User-Agent': 'KeepAliveBot/1.0' }
    });

    if (response.ok) {
      console.log(`✅ 成功: ${url} (状态: ${response.status})`);
    } else {
      console.warn(`⚠️ 注意: ${url} (状态: ${response.status} - ${response.statusText})`);
    }
  } catch (error) {
    if (error.name === 'AbortError') {
      console.warn(`⌛️ 超时: ${url} (超过 ${TIMEOUT / 1000} 秒)`);
    } else {
      let errorDetails = error.message;
      if (error.cause) {
        // error.cause 可能是 Error 对象，也可能只是一个字符串或对象
        // 尝试获取更具体的错误代码或消息
        const causeMessage = error.cause.message || error.cause.code || String(error.cause);
        errorDetails += ` (底层原因: ${causeMessage})`;
      }
      console.warn(`❌ 访问失败: ${url}, 错误: ${errorDetails}`);
    }
  } finally {
    clearTimeout(timeoutId);
  }
}

async function handleTask() {
  console.log('⏳ 任务开始');

  if (urls.length === 0) {
    console.warn('⚠️ URL列表为空或格式不正确。请检查环境变量 KEEPALIVE_URLS 或脚本中的 defaultUrlString 配置。');
    console.warn('   确保URL以 http:// 或 https:// 开头，并使用空格或逗号分隔。');
    console.log('📊 任务结束 (无有效URL)');
    return;
  }

  console.log(`🔍 计划访问的URL (${urls.length}个): ${urls.join(', ')}`);

  // 使用 Promise.allSettled 可以等待所有 promise 完成，无论成功或失败，
  // 并且可以获取每个 promise 的结果。
  // 对于这个保活脚本，Promise.all 也适用，因为它主要关注副作用（打印日志）。
  // 这里我们继续使用 Promise.all，因为它更简洁，并且错误已经在 fetchWithTimeout 中处理。
  await Promise.all(urls.map(url => fetchWithTimeout(url)));

  console.log('📊 任务结束');
}

// 当脚本被执行时（例如通过青龙面板的定时任务），直接调用该函数
handleTask().catch(err => {
  console.error("💥 脚本执行时发生未捕获的严重错误:", err);
  // 在某些环境中，可能需要设置退出码以表明脚本执行失败
  if (typeof process !== 'undefined' && process.exitCode !== undefined) {
    process.exitCode = 1;
  }
});
