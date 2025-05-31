// 脚本说明：
// 这是一个Node.js脚本，用于检查一组URL的可访问性。
// 它将按顺序访问URL，并在每个请求后可选地暂停一小段时间。
// 适合在青龙面板等环境中作为定时任务运行。

// --- 配置区 ---

// 优先从环境变量 KEEPALIVE_JS_URLS 读取URL列表
const urlsEnv = process.env.KEEPALIVE_JS_URLS;
const defaultUrlString = 'https://liii.zabc.net,https://dingyue.zabc.net,https://llli.zabc.net,https://sasa.zabc.net';
// const defaultUrlString = 'https://liii.zabc.net,https://dingyue.zabc.net,https://llli.zabc.net,https://lljj.zabc.net,https://sasa.zabc.net,https://fl.opb.dpdns.org/65abc702-dde4-4e84-8244-e79273981297,https://am.opb.dpdns.org/f8ff1eb2-97c1-4469-ebe1-8f13293ddcb6';

const urlString = urlsEnv || defaultUrlString;

const urls = urlString
  .split(/[\s,，]+/)
  .map(url => url.trim())
  .filter(url => url && (url.startsWith('http://') || url.startsWith('https://')));

const TIMEOUT = 30000; // 请求超时时间（毫秒），例如 30000ms = 30秒
const DELAY_BETWEEN_REQUESTS = 1000; // 每个请求之间的延迟时间（毫秒），例如 1000ms = 1秒。设为0则无延迟。
const USER_AGENT = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36 QinglongPanel-KeepAliveJS/1.0';

// --- 配置区结束 ---

// Node.js v18+ 版本全局自带 fetch 和 AbortController。
// 如果Node.js版本较低，需要安装 node-fetch (npm install node-fetch)
// 然后取消下面一行的注释:
// const fetch = (...args) => import('node-fetch').then(({default: fetch}) => fetch(...args));

async function fetchWithTimeout(url) {
  const controller = new AbortController();
  const timeoutId = setTimeout(() => {
    controller.abort();
  }, TIMEOUT);

  const timestamp = new Date().toISOString().replace('T', ' ').substring(0, 19);

  try {
    const response = await fetch(url, {
      signal: controller.signal,
      headers: {
        'User-Agent': USER_AGENT,
      },
      redirect: 'follow',
    });

    if (response.ok) {
      console.log(`✅ [${timestamp}] 成功: ${url} (状态: ${response.status})`);
    } else {
      console.warn(`⚠️ [${timestamp}] 注意: ${url} (状态: ${response.status} - ${response.statusText})`);
    }
  } catch (error) {
    if (error.name === 'AbortError') {
      console.warn(`⌛️ [${timestamp}] 超时: ${url} (超过 ${TIMEOUT / 1000} 秒)`);
    } else {
      let errorDetails = error.message;
      if (error.cause) {
        const causeMessage = error.cause.message || error.cause.code || String(error.cause);
        errorDetails += ` (底层原因: ${causeMessage})`;
      }
      console.warn(`❌ [${timestamp}] 访问失败: ${url}, 错误: ${errorDetails}`);
    }
  } finally {
    clearTimeout(timeoutId);
  }
}

async function handleKeepAliveTask() {
  const startTime = new Date();
  const startTimestamp = startTime.toISOString().replace('T', ' ').substring(0, 19);
  console.log(`⏳ 任务开始 (${startTimestamp}) - 按顺序执行请求`);

  if (urls.length === 0) {
    console.warn('⚠️ URL列表为空或格式不正确。请检查环境变量 KEEPALIVE_JS_URLS 或脚本中的 defaultUrlString 配置。');
    console.warn('   确保URL以 http:// 或 https:// 开头，并使用空格或逗号分隔。');
    console.log(`📊 任务结束 (无有效URL)`);
    return;
  }

  console.log(`🔍 计划访问的URL (${urls.length}个): ${urls.join(', ')}`);
  console.log(`   单次请求超时: ${TIMEOUT / 1000} 秒`);
  if (DELAY_BETWEEN_REQUESTS > 0) {
    console.log(`   请求间延迟: ${DELAY_BETWEEN_REQUESTS / 1000} 秒`);
  }
  console.log("---");

  // *** 修改部分：按顺序执行请求 ***
  for (const url of urls) {
    await fetchWithTimeout(url); // 等待当前请求完成后再进行下一个

    // 如果设置了请求间延迟，则在此处暂停
    if (DELAY_BETWEEN_REQUESTS > 0 && urls.indexOf(url) < urls.length - 1) { // 最后一个URL之后不需要延迟
      // console.log(`   ...等待 ${DELAY_BETWEEN_REQUESTS / 1000} 秒...`); // 可选的调试日志
      await new Promise(resolve => setTimeout(resolve, DELAY_BETWEEN_REQUESTS));
    }
  }
  // *** 修改结束 ***
  
  console.log("---");
  const endTime = new Date();
  const endTimestamp = endTime.toISOString().replace('T', ' ').substring(0, 19);
  const duration = ((endTime - startTime) / 1000).toFixed(2);
  console.log(`📊 任务结束 (${endTimestamp}) 耗时 ${duration} 秒`);
}

handleKeepAliveTask().catch(err => {
  const errorTimestamp = new Date().toISOString().replace('T', ' ').substring(0, 19);
  console.error(`💥 [${errorTimestamp}] 脚本执行时发生未捕获的严重错误:`, err);
  if (typeof process !== 'undefined' && process.exitCode !== undefined) {
    process.exitCode = 1;
  }
});
