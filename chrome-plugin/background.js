chrome.action.onClicked.addListener((tab) => {
  chrome.sidePanel.open({ windowId: tab.windowId })
    .catch(() => console.error('Failed to open Mirror Panel.'));
});
