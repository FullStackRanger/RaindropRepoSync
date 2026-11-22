// Must match the port the clipper listens on (web_clipper.py --port, the macOS app's Settings, or
// WEB_CLIPPER_PORT) and host_permissions.
const CLIPPER = "http://127.0.0.1:47811";

function flash(tabId, text, color, title) {
  chrome.action.setBadgeBackgroundColor({ tabId, color });
  chrome.action.setBadgeText({ tabId, text });
  chrome.action.setTitle({ tabId, title });
  setTimeout(() => {
    chrome.action.setBadgeText({ tabId, text: "" });
    chrome.action.setTitle({ tabId, title: "Clip this page to Markdown" });
  }, text === "OK" ? 2000 : 6000);
}

chrome.action.onClicked.addListener(async (tab) => {
  const url = tab.url || "";
  if (!/^https?:\/\//i.test(url)) {
    flash(tab.id, "!", "#cf222e", "Only http(s) pages can be clipped.");
    return;
  }
  try {
    const response = await fetch(`${CLIPPER}/clip?format=json&url=${encodeURIComponent(url)}`);
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    flash(tab.id, "OK", "#1a7f37", "Sent to Web Clipper");
  } catch (err) {
    flash(tab.id, "!", "#cf222e",
      "Web Clipper isn't running. Open the Web Clipper app (or run python web_clipper.py) (" + err.message + ")");
  }
});
