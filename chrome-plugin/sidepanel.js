const doCrawl = document.getElementById('doCrawl');
const saveBtn = document.getElementById('saveBtn');
const statusDiv = document.getElementById('statusDiv');
let isCrawlActive = false;

function updateButtonState() {
  if (isCrawlActive) {
    saveBtn.textContent = "Stop Crawl";
    saveBtn.style.background = "#dc3545";
  } else if (doCrawl.checked) {
    saveBtn.textContent = "Start Crawl";
    saveBtn.style.background = "#28a745";
  } else {
    saveBtn.textContent = "Save Current Page";
    saveBtn.style.background = "#007bff";
  }
}

doCrawl.addEventListener('change', updateButtonState);

saveBtn.addEventListener('click', async () => {
  if (isCrawlActive) {
    // Stop crawl
    try {
      await fetch('http://localhost:8765/stop', { method: 'POST' });
    } catch (e) {
      console.error("Failed to stop crawl:", e);
    }
    return;
  }

  let [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  if (tab && tab.url) {
    const isCrawlChecked = document.getElementById('doCrawl').checked;
    const maxDepth = parseInt(document.getElementById('maxDepth').value, 10) || 0;
    const forceRefresh = document.getElementById('forceRefresh').checked;
    const outFile = document.getElementById('outFile').value.trim();
    
    let injectionResults = await chrome.scripting.executeScript({
      target: { tabId: tab.id },
      func: () => document.documentElement.outerHTML
    });
    const html = injectionResults[0]?.result;
    
    const endpoint = isCrawlChecked ? '/crawl' : '/save';
    const payload = { url: tab.url, html: html, force_refresh: forceRefresh };
    if (isCrawlChecked) payload.max_depth = maxDepth;
    if (outFile) payload.out_file = outFile;

    try {
      await fetch(`http://localhost:8765${endpoint}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });
      // Force quick refresh
      setTimeout(refreshList, 500);
    } catch (err) {
      alert("Error communicating with crawler. Is text_mirror.py running with --serve on port 8765?");
    }
  }
});

async function refreshList() {
  try {
    const response = await fetch('http://localhost:8765/list');
    const data = await response.json();
    
    isCrawlActive = data.crawl_active;
    updateButtonState();
    
    if (isCrawlActive) {
      statusDiv.style.display = 'block';
      document.getElementById('statDiscovered').textContent = data.stats.discovered;
      document.getElementById('statDownloaded').textContent = data.stats.downloaded;
      document.getElementById('statQueue').textContent = data.stats.in_queue;
    } else {
      statusDiv.style.display = 'none';
    }
    
    if (data.saved_urls) {
      const ul = document.getElementById('linkList');
      ul.innerHTML = '';
      [...data.saved_urls].reverse().forEach(url => {
        let li = document.createElement('li');
        li.textContent = url;
        ul.appendChild(li);
      });
    }
  } catch (err) {
    console.error("Refresh failed:", err);
  }
}

refreshList();
setInterval(refreshList, 1000);
