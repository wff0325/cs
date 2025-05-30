// 每个保活网页之间用空格或者，或者,间隔开，网页前带https://
const urlString = 'https://fl.opb.dpdns.org/65abc702-dde4-4e84-8244-e79273981297,https://am.opb.dpdns.org/f8ff1eb2-97c1-4469-ebe1-8f13293ddcb6'; // 你可以修改这里，或者使用环境变量
const urls = urlString.split(/[\s,，]+/).filter(url => url.startsWith('http')); // 确保分割后是有效的URL前缀
const TIMEOUT = 5000; // 5 秒

// Node.js v18+ 版本全局自带 fetch。如果你的 Node.js 版本较低，可能需要安装 'node-fetch'。
// 青龙面板通常运行较新的 Node.js 版本，所以全局 fetch 应该是可用的。
// AbortController 在较新的 Node.js 版本中也是全局可用的。

async function fetchWithTimeout(url) {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), TIMEOUT);
  try {
    // Node.js v18+ 全局可用 fetch
    // 如果是旧版本，你可能需要这样：
    // const fetch = (await import('node-fetch')).default;
    const response = await fetch(url, { signal: controller.signal });
    // 你可能想检查 response.ok 或 response.status 来更精确地判断成功
    console.log(`✅ 成功: ${url} (状态: ${response.status})`);
  } catch (error) {
    if (error.name === 'AbortError') {
      console.warn(`⌛️ 超时: ${url} (超过 ${TIMEOUT/1000} 秒)`);
    } else {
      console.warn(`❌ 访问失败: ${url}, 错误: ${error.message}`);
    }
  } finally {
    clearTimeout(timeout);
  }
}

async function handleTask() { // 从 handleScheduled 重命名为 handleTask，更清晰
  console.log('⏳ 任务开始');
  if (urls.length === 0 || (urls.length === 1 && urls[0] === '')) {
    console.warn('⚠️ URL列表为空或格式不正确，请检查 urlString 配置。确保URL以 http(s):// 开头。');
    console.log('📊 任务结束');
    return;
  }
  console.log(`🔍 计划访问的URL (${urls.length}个): ${urls.join(', ')}`);
  await Promise.all(urls.map(fetchWithTimeout));
  console.log('📊 任务结束');
}

// 当脚本被青龙执行时，直接调用该函数
handleTask().catch(err => {
  console.error("脚本执行时发生未捕获的错误:", err);
  process.exitCode = 1; // 可选：标记一个错误退出码
});
