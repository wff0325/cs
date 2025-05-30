// 脚本说明：
// 这是一个Node.js脚本，用于检查一组URL的可访问性。
// 它适合在青龙面板等环境中作为定时任务运行。
// 脚本会尝试访问每个URL，并记录成功、失败或超时的情况。

// --- 配置区 ---

// 优先从环境变量 KEEPALIVE_JS_URLS 读取URL列表
// 格式：URL1,URL2, URL3 (逗号或空格分隔)
// 如果环境变量未设置，则使用下面的 defaultUrlString
const urlsEnv = process.env.KEEPALIVE_JS_URLS;
const defaultUrlString = 'https://liii.zabc.net,https://dingyue.zabc.net,https://llli.zabc.net,https://lljj.zabc.net,https://sasa.zabc.net';
// const defaultUrlString = 'https://liii.zabc.net,https://dingyue.zabc.net,https://llli.zabc.net,https://lljj.zabc.net,https://sasa.zabc.net,https://fl.opb.dpdns.org/65abc702-dde4-4e84-8244-e79273981297,https://am.opb.dpdns.org/f8ff1eb2-97c1-4469-ebe1-8f13293ddcb6';


const urlString = urlsEnv || defaultUrlString;

const urls = urlString
  .split(/[\s,，]+/) // 使用正则表达式分割，支持空格、英文逗号、中文逗号
  .map(url => url.trim()) // 去除每个URL两端的空白字符
  .filter(url => url && (url.startsWith('http://') || url.startsWith('https://'))); // 确保URL不为空且以 http(s):// 开头

const TIMEOUT = 30000; // 请求超时时间（毫秒），例如 10000ms = 10秒
const USER_AGENT = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36 QinglongPanel-KeepAliveJS/1.0';

// --- 配置区结束 ---

// Node.js v18+ 版本全局自带 fetch 和 AbortController。
// 如果Node.js版本较低，需要安装 node-fetch (npm install node-fetch)
// 然后取消下面一行的注释:
// const fetch = (...args) => import('node-fetch').then(({default: fetch}) => fetch(...args));
// 对于青龙面板，通常Node.js版本较新，全局fetch可用。

async function fetchWithTimeout(url) {
  const controller = new AbortController();
  const timeoutId = setTimeout(() => {
    controller.abort();
  }, TIMEOUT);

  const timestamp = new Date().toISOString().replace('T', ' ').substring(0, 19); // YYYY-MM-DD HH:MM:SS

  try {
    const response = await fetch(url, {
      signal: controller.signal,
      headers: {
        'User-Agent': USER_AGENT,
      },
      redirect: 'follow', // 跟随重定向
    });

    if (response.ok) { // status in the range 200-299
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
  console.log(`⏳ 任务开始 (${startTimestamp})`);

  if (urls.length === 0) {
    console.warn('⚠️ URL列表为空或格式不正确。请检查环境变量 KEEPALIVE_JS_URLS 或脚本中的 defaultUrlString 配置。');
    console.warn('   确保URL以 http:// 或 https:// 开头，并使用空格或逗号分隔。');
    console.log(`📊 任务结束 (无有效URL)`);
    return;
  }

  console.log(`🔍 计划访问的URL (${urls.length}个): ${urls.join(', ')}`);
  console.log(`   单次请求超时: ${TIMEOUT / 1000} 秒`);
  console.log("---");

  // 使用 Promise.allSettled 等待所有请求完成，无论成功或失败
  // 或者使用 Promise.all 如果你希望任何一个请求失败就让整个 Promise.all 失败 (但不推荐用于此场景)
  // 这里我们简单地用 for...of 循环串行或 Promise.all 并行处理
  // 为了避免短时间内对服务器造成大量并发（如果URL很多），可以考虑串行或者分批并行
  // 对于少量URL，Promise.all 是可以的。

  // 并行处理:
  await Promise.all(urls.map(url => fetchWithTimeout(url)));

  // 如果需要串行处理（一个接一个）:
  // for (const url of urls) {
  //   await fetchWithTimeout(url);
  //   // 可以在每个请求后加入短暂延时
  //   // await new Promise(resolve => setTimeout(resolve, 500)); // 暂停0.5秒
  // }
  
  console.log("---");
  const endTime = new Date();
  const endTimestamp = endTime.toISOString().replace('T', ' ').substring(0, 19);
  const duration = ((endTime - startTime) / 1000).toFixed(2); // 耗时，秒，保留两位小数
  console.log(`📊 任务结束 (${endTimestamp}) 耗时 ${duration} 秒`);
}

// 当脚本被执行时（例如通过青龙面板的定时任务），直接调用该函数
handleKeepAliveTask().catch(err => {
  const errorTimestamp = new Date().toISOString().replace('T', ' ').substring(0, 19);
  console.error(`💥 [${errorTimestamp}] 脚本执行时发生未捕获的严重错误:`, err);
  // 在某些环境中，可能需要设置退出码以表明脚本执行失败
  if (typeof process !== 'undefined' && process.exitCode !== undefined) {
    process.exitCode = 1;
  }
});
