const API_BASE = 'http://localhost:8765';
const REQUEST_TIMEOUT_MS = 10000;
const POLL_INTERVAL_MS = 1000;
const doCrawl = document.getElementById('doCrawl');
const saveBtn = document.getElementById('saveBtn');
const statusDiv = document.getElementById('statusDiv');
const feedback = document.getElementById('feedback');
let isCrawlActive = false;
let actionPending = false;

function updateButtonState() {
  saveBtn.disabled = actionPending;
  saveBtn.textContent = isCrawlActive ? 'Stop Crawl' : doCrawl.checked ? 'Start Crawl' : 'Save Current Page';
  saveBtn.style.background = isCrawlActive ? '#dc3545' : doCrawl.checked ? '#28a745' : '#007bff';
}

function showError(message) {
  feedback.textContent = message;
  console.error('Mirror panel operation failed:', message);
}

async function request(path, payload) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);
  try {
    const response = await fetch(API_BASE + path, {
      signal: controller.signal,
      ...(payload === undefined ? {} : {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      })
    });
    if (!response.ok) {
      throw new Error(`Crawler returned HTTP ${response.status}. Check the local server.`);
    }
    return await response.json();
  } finally {
    clearTimeout(timer);
  }
}

doCrawl.addEventListener('change', updateButtonState);
saveBtn.addEventListener('click', async () => {
  if (actionPending) return;
  actionPending = true;
  feedback.textContent = '';
  updateButtonState();
  try {
    if (isCrawlActive) {
      await request('/stop', {});
      feedback.textContent = 'Stop requested.';
    } else {
      const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
      if (!tab || !/^https?:\/\//i.test(tab.url || '')) {
        throw new Error('Select a public HTTP or HTTPS page to save.');
      }
      const depth = Number(document.getElementById('maxDepth').value);
      if (!Number.isSafeInteger(depth) || depth < 0) {
        throw new Error('Max depth must be a nonnegative integer; 0 means unlimited.');
      }
      const results = await chrome.scripting.executeScript({
        target: { tabId: tab.id }, func: () => ({ url: location.href, html: document.documentElement.outerHTML })
      });
      const captured = results?.[0]?.result;
      if (!captured || typeof captured.html !== 'string' || !captured.html
          || typeof captured.url !== 'string' || !/^https?:\/\//i.test(captured.url)) {
        throw new Error('Could not read the selected page.');
      }
      const payload = { url: captured.url, html: captured.html,
        force_refresh: document.getElementById('forceRefresh').checked };
      const outFile = document.getElementById('outFile').value.trim();
      if (outFile) payload.out_file = outFile;
      if (doCrawl.checked) payload.max_depth = depth;
      await request(doCrawl.checked ? '/crawl' : '/save', payload);
      feedback.textContent = doCrawl.checked ? 'Crawl started.' : 'Page saved.';
    }
    await refreshList();
  } catch (error) {
    showError(error instanceof Error ? error.message : 'Crawler request failed.');
  } finally {
    actionPending = false;
    updateButtonState();
  }
});

let refreshPending = false;
async function refreshList() {
  if (refreshPending) return;
  refreshPending = true;
  try {
    const data = await request('/list');
    if (!data || typeof data.crawl_active !== 'boolean' || !Array.isArray(data.saved_urls)
        || data.saved_urls.some(url => typeof url !== 'string')
        || (data.crawl_active && (!data.stats || typeof data.stats !== 'object'
          || ['discovered', 'downloaded', 'in_queue'].some(key => !Number.isFinite(data.stats[key]) || data.stats[key] < 0)))) {
      throw new Error('Crawler returned invalid status data.');
    }
    isCrawlActive = data.crawl_active;
    updateButtonState();
    statusDiv.style.display = isCrawlActive ? 'block' : 'none';
    if (isCrawlActive) {
      for (const [key, id] of [['discovered', 'statDiscovered'], ['downloaded', 'statDownloaded'], ['in_queue', 'statQueue']]) {
        document.getElementById(id).textContent = data.stats[key];
      }
    }
    const ul = document.getElementById('linkList');
    ul.replaceChildren();
    [...data.saved_urls].reverse().forEach(url => {
      const li = document.createElement('li');
      li.textContent = url;
      ul.appendChild(li);
    });
  } catch (error) {
    showError(error instanceof Error ? error.message : 'Status refresh failed.');
  } finally {
    refreshPending = false;
  }
}

async function poll() {
  await refreshList();
  setTimeout(poll, POLL_INTERVAL_MS);
}
poll();
