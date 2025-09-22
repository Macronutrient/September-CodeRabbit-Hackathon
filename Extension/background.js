// AI Tab Organizer - Background Service Worker (MV3)
// - Reads OpenAI API key from chrome.storage.sync (set via options page)
// - Emits real-time progress events to the popup via chrome.runtime.sendMessage
// - Analyzes tabs with GPT-4.1 and organizes/cleans them
// - Supports Undo of the last action (closing/grouping)

let isProcessing = false;

// Persist details to support Undo of the last action (chrome.storage.local)
// Structure example:
// { type: 'close' | 'organize' | 'group',
//   closedTabs?: Array<{url, windowId, index, active, pinned}>,
//   groupedTabIds?: Array<number[]>,
//   timestamp: number }
async function setLastAction(action) {
  try {
    await chrome.storage.local.set({ lastAction: { ...action, timestamp: Date.now() } });
  } catch (e) {
    console.warn("Failed to persist lastAction:", e);
  }
}
async function getLastAction() {
  try {
    const { lastAction } = await chrome.storage.local.get(["lastAction"]);
    return lastAction || null;
  } catch (e) {
    console.warn("Failed to read lastAction:", e);
    return null;
  }
}
async function clearLastAction() {
  try {
    await chrome.storage.local.remove(["lastAction"]);
  } catch (e) {
    console.warn("Failed to clear lastAction:", e);
  }
}

function sendProgress(stage, data = {}) {
  try {
    chrome.runtime.sendMessage({ type: "progress", stage, ...data });
  } catch (e) {
    // No listeners (e.g., popup closed) - ignore
  }
}

// Initialize extension defaults
chrome.runtime.onInstalled.addListener(() => {
  chrome.storage.sync.set({
    importanceThreshold: 5,
    autoClose: false,
    autoOrganize: false, // auto-organize disabled by default
    // Defaults for provider/model selections (requested behavior)
    providerAuto: "gemini",
    modelAuto: "gemini-2.5-flash-lite",
  });
  console.log("AI Tab Organizer installed");
});

// Listen for messages from popup
chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
  (async () => {
    switch (request.action) {
      case "organizeTabsAndClose":
        await organizeTabsAndClose(request.settings || {});
        sendResponse({ success: true });
        break;

      case "debugCreateTabs":
        await createDebugTabs();
        sendResponse({ success: true });
        break;

      case "debugCloseAllTabs":
        await debugCloseAllTabs();
        sendResponse({ success: true });
        break;

      case "closeLowImportance":
        await closeLowImportance(request.settings || {});
        sendResponse({ success: true });
        break;

      case "undoLastAction":
        await undoLastAction();
        sendResponse({ success: true });
        break;

      case "getTabCount": {
        const tabs = await chrome.tabs.query({});
        sendResponse({ count: tabs.length });
        break;
      }

      case "getStoredSettings": {
        const data = await chrome.storage.sync.get([
          "importanceThreshold",
          "autoClose",
          "autoOrganize",
          // API keys
          "apiKey",        // OpenAI
          "geminiKey",     // Google Gemini
          "claudeKey",     // Anthropic Claude
          // Provider/model selections
          "providerAnalyze",
          "modelAnalyze",
          "providerClose",
          "modelClose",
          "providerAuto",
          "modelAuto",
        ]);
        sendResponse(data);
        break;
      }

      default:
        sendResponse({ success: false, error: "Unknown action" });
    }
  })();
  // Keep the message channel open for async response
  return true;
});

// Auto-organize on new tabs / URL changes using Gemini 2.5 Flash Lite
let autoOrganizeTimer = null;
async function autoOrganizeIfEnabled(trigger, tabId) {
  try {
    const {
      autoOrganize,
      geminiKey,
      importanceThreshold,
      apiKey,
      claudeKey,
      providerAuto,
      modelAuto,
    } = await chrome.storage.sync.get([
      "autoOrganize",
      "geminiKey",
      "importanceThreshold",
      "apiKey",
      "claudeKey",
      "providerAuto",
      "modelAuto",
    ]);
    if (!autoOrganize) return;

    // If no key in storage, the user provided a default key in request. Use as fallback.
    const effectiveGeminiKey = geminiKey && geminiKey.trim()
      ? geminiKey.trim()
      : "AIzaSyC8TO-gwnznKxEHbiYvwY8dLKkL2w1fGas";

    // Debounce to avoid excessive calls on rapid updates
    if (autoOrganizeTimer) clearTimeout(autoOrganizeTimer);
    autoOrganizeTimer = setTimeout(() => {
      const provider = (providerAuto || "gemini").toLowerCase();
      const model =
        modelAuto ||
        (provider === "gemini"
          ? "gemini-2.5-flash-lite"
          : provider === "openai"
          ? "gpt-4.1"
          : "claude-3-5-sonnet-latest");

      organizeTabsGeneric({
        provider,
        model,
        keys: { apiKey, geminiKey: effectiveGeminiKey, claudeKey },
        importanceThreshold: typeof importanceThreshold === "number" ? importanceThreshold : 5,
        autoClose: false, // no auto-close in auto mode
      });
    }, 1500);
  } catch (e) {
    console.warn("autoOrganizeIfEnabled failed:", e);
  }
}

const recentTouch = new Map();
chrome.tabs.onCreated.addListener((tab) => {
  if (tab && typeof tab.id === "number") recentTouch.set(tab.id, Date.now());
  // Do not auto-organize on creation; wait for completed load
});
chrome.tabs.onUpdated.addListener((tabId, changeInfo, tab) => {
  if (changeInfo.status === "complete") {
    if (typeof tabId === "number") recentTouch.set(tabId, Date.now());
    autoOrganizeIfEnabled("updated", tabId);
  }
});

// Organized flow using Gemini (analyze + close + group)
async function organizeTabsWithGemini({ geminiKey, importanceThreshold, autoClose }) {
  if (isProcessing) return;
  isProcessing = true;
  sendProgress("start");

  try {
    const tabs = await chrome.tabs.query({});
    sendProgress("tabs_collected", { total: tabs.length });

    const tabData = [];
    for (let i = 0; i < tabs.length; i++) {
      const t = tabs[i];
      let content = {};
      try {
        content = await extractTabContent(t);
      } catch (_e) {}
      tabData.push({
        id: t.id,
        url: t.url,
        title: t.title,
        content,
        favIconUrl: t.favIconUrl,
      });
      sendProgress("extract_progress", {
        completed: i + 1,
        total: tabs.length,
        tab: { id: t.id, title: t.title, url: t.url },
      });
    }

    sendProgress("ai_request", { totalTabs: tabData.length });
    const analysis = await analyzeTabsWithGemini(tabData, { geminiKey, importanceThreshold });
    sendProgress("ai_response", {
      tabsToClose: Array.isArray(analysis.tabsToClose) ? analysis.tabsToClose.length : 0,
      groups: Array.isArray(analysis.tabGroups) ? analysis.tabGroups.length : 0,
      reasoning: typeof analysis.reasoning === "string" ? analysis.reasoning.slice(0, 300) : "",
    });

    const idToTab = new Map();
    tabs.forEach((t) => idToTab.set(t.id, t));
    const closedTabsMeta = [];

    // Protect active tab(s), internal pages, and very recent tabs from being closed
    const protectActive = new Set(tabs.filter(t => t && t.active).map(t => t.id));
    const nowTs = Date.now();
    if (Array.isArray(analysis.tabsToClose)) {
      analysis.tabsToClose = analysis.tabsToClose.filter((tid) => {
        const original = idToTab.get(tid);
        if (!original) return false; // if tab no longer exists, skip
        const url = original.url || "";
        // Never close active tab
        if (protectActive.has(tid)) return false;
        // Never close internal/new tab pages
        if (url.startsWith("chrome://") || url.startsWith("chrome-extension://") || url === "about:blank" || url.includes("newtab")) return false;
        // Never close tabs updated very recently (e.g., last 30s)
        const touched = recentTouch.get(tid);
        if (touched && nowTs - touched < 30000) return false;
        return true;
      });
    }
    if (autoClose && Array.isArray(analysis.tabsToClose)) {
      let closed = 0;
      for (const tabId of analysis.tabsToClose) {
        try {
          const original = idToTab.get(tabId);
          if (original && original.url) {
            closedTabsMeta.push({
              url: original.url,
              windowId: original.windowId,
              index: original.index,
              active: !!original.active,
              pinned: !!original.pinned,
            });
          }
          await chrome.tabs.remove(tabId);
          closed++;
          sendProgress("closing_progress", { closed, total: analysis.tabsToClose.length, tabId });
        } catch (_e) {}
      }
      sendProgress("closing_done", { closed });
    }

    const groupedTabIds = [];
    if (Array.isArray(analysis.tabGroups) && analysis.tabGroups.length) {
      let grouped = 0;
      for (const group of analysis.tabGroups) {
        try {
          if (!Array.isArray(group.tabIds) || !group.tabIds.length) continue;
          const gid = await chrome.tabs.group({ tabIds: group.tabIds });
          await chrome.tabGroups.update(gid, {
            title: group.name,
            color: group.color || "purple",
          });
          grouped++;
          groupedTabIds.push([...group.tabIds]);
          sendProgress("group_progress", {
            grouped,
            total: analysis.tabGroups.length,
            name: group.name,
            count: group.tabIds?.length ?? 0,
          });
        } catch (_e) {}
      }
      sendProgress("grouping_done", { groupsCreated: grouped });
    }

    await setLastAction({
      type: autoClose ? (groupedTabIds.length ? "organize" : "close") : (groupedTabIds.length ? "group" : "none"),
      closedTabs: closedTabsMeta,
      groupedTabIds,
    });

    sendProgress("complete", { success: true });
  } catch (e) {
    console.error("organizeTabsWithGemini error:", e);
    sendProgress("error", { message: String(e?.message || e) });
  } finally {
    isProcessing = false;
  }
}

// Analyze tabs with Gemini 2.5 Flash Lite
async function analyzeTabsWithGemini(tabData, { geminiKey, importanceThreshold }) {
  const prompt = `You are an AI that organizes browser tabs. Analyze the following ${tabData.length} tabs and:
1) Rate each tab's importance 1-10 for relevance, value, recency, importance, uniqueness.
2) Suggest closing tabs with importance < ${importanceThreshold}.
3) Group remaining tabs (max 8) with a name and a Chrome group color: "blue","red","yellow","green","pink","purple","cyan","orange".
Return ONLY minified JSON with schema:
{"tabsToClose":[tabId,...],"tabGroups":[{"name":"Group Name","color":"purple","tabIds":[ids...]}],"reasoning":"short" }

Tabs:
${tabData
  .map(
    (t, i) =>
      `Tab ${i + 1}:
- id: ${t.id}
- title: ${t.title}
- url: ${t.url}
- content: ${JSON.stringify(t.content).slice(0, 300)}...`
  )
  .join("\n")}`;

  try {
    const res = await fetch(
      "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash-lite:generateContent?key=" +
        encodeURIComponent(geminiKey),
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          contents: [{ role: "user", parts: [{ text: prompt }] }],
          generationConfig: { temperature: 0.2, maxOutputTokens: 900 },
        }),
      }
    );

    if (!res.ok) {
      const errText = await res.text().catch(() => "");
      throw new Error(`Gemini API error: ${res.status} ${errText}`);
    }

    const data = await res.json();
    const text =
      data?.candidates?.[0]?.content?.parts?.[0]?.text ||
      data?.candidates?.[0]?.content?.parts?.[0]?.rawText ||
      "{}";

    // Parse JSON (may include code fences)
    let parsed;
    try {
      parsed = JSON.parse(text);
    } catch {
      const start = text.indexOf("{");
      const end = text.lastIndexOf("}");
      if (start >= 0 && end > start) {
        parsed = JSON.parse(text.slice(start, end + 1));
      } else {
        throw new Error("Gemini response was not valid JSON");
      }
    }
    if (!Array.isArray(parsed.tabsToClose)) parsed.tabsToClose = [];
    if (!Array.isArray(parsed.tabGroups)) parsed.tabGroups = [];
    return parsed;
  } catch (e) {
    console.error("analyzeTabsWithGemini error:", e);
    return {
      tabsToClose: [],
      tabGroups: [
        { name: "All Tabs", color: "purple", tabIds: tabData.map((t) => t.id) },
      ],
      reasoning: "Gemini error - basic grouping applied",
    };
  }
}

/**
 * Generic analyzers and routing by provider/model
 */
async function analyzeTabsWithOpenAI(tabData, { apiKey, model, importanceThreshold }) {
  const prompt = `You are an AI that organizes browser tabs. Analyze the following ${tabData.length} tabs and:
1) Rate each tab's importance from 1-10 based on content relevance, value, recency, professional/personal importance, uniqueness.
2) Suggest closing tabs with importance < ${importanceThreshold}.
3) Group remaining tabs into logical categories (max 8 groups). Use Chrome tab group colors: "blue","red","yellow","green","pink","purple","cyan","orange".

Tabs:
${tabData
  .map(
    (t, i) =>
      `Tab ${i + 1}:
- id: ${t.id}
- title: ${t.title}
- url: ${t.url}
- content: ${JSON.stringify(t.content).slice(0, 300)}...`
  )
  .join("\n")}

Respond ONLY with minified JSON of this shape (no markdown, no extra text):
{"tabsToClose":[tabId,...],"tabGroups":[{"name":"Group Name","color":"purple","tabIds":[ids...]}],"reasoning":"short string"}`;

  try {
    const res = await fetch("https://api.openai.com/v1/chat/completions", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${apiKey}`,
      },
      body: JSON.stringify({
        model: model || "gpt-4.1",
        messages: [{ role: "user", content: prompt }],
        temperature: 0.3,
        max_tokens: 900,
      }),
    });

    if (!res.ok) {
      const errText = await res.text().catch(() => "");
      throw new Error(`OpenAI API error: ${res.status} ${errText}`);
    }

    const data = await res.json();
    const content = data?.choices?.[0]?.message?.content || "{}";
    let parsed;
    try {
      parsed = JSON.parse(content);
    } catch {
      const start = content.indexOf("{");
      const end = content.lastIndexOf("}");
      if (start >= 0 && end > start) parsed = JSON.parse(content.slice(start, end + 1));
      else throw new Error("OpenAI response was not valid JSON");
    }
    if (!Array.isArray(parsed.tabsToClose)) parsed.tabsToClose = [];
    if (!Array.isArray(parsed.tabGroups)) parsed.tabGroups = [];
    return parsed;
  } catch (e) {
    console.error("analyzeTabsWithOpenAI error:", e);
    return {
      tabsToClose: [],
      tabGroups: [{ name: "All Tabs", color: "purple", tabIds: tabData.map((t) => t.id) }],
      reasoning: "OpenAI error - basic grouping applied",
    };
  }
}

async function analyzeTabsWithClaude(tabData, { claudeKey, model, importanceThreshold }) {
  const prompt = `You are an AI that organizes browser tabs. Analyze the following ${tabData.length} tabs and:
1) Rate each tab's importance 1-10 (relevance, value, recency, importance, uniqueness).
2) Suggest closing tabs with importance < ${importanceThreshold}.
3) Group remaining tabs (max 8) with a name and a Chrome group color: "blue","red","yellow","green","pink","purple","cyan","orange".
Return ONLY minified JSON with schema:
{"tabsToClose":[tabId,...],"tabGroups":[{"name":"Group Name","color":"purple","tabIds":[ids...]}],"reasoning":"short" }

Tabs:
${tabData
  .map(
    (t, i) =>
      `Tab ${i + 1}:
- id: ${t.id}
- title: ${t.title}
- url: ${t.url}
- content: ${JSON.stringify(t.content).slice(0, 300)}...`
  )
  .join("\n")}`;

  try {
    const res = await fetch("https://api.anthropic.com/v1/messages", {
      method: "POST",
      headers: {
        "content-type": "application/json",
        "x-api-key": claudeKey,
        "anthropic-version": "2023-06-01",
      },
      body: JSON.stringify({
        model: model || "claude-3-5-sonnet-latest",
        max_tokens: 900,
        temperature: 0.2,
        messages: [
          {
            role: "user",
            content: [{ type: "text", text: prompt }],
          },
        ],
      }),
    });

    if (!res.ok) {
      const errText = await res.text().catch(() => "");
      throw new Error(`Claude API error: ${res.status} ${errText}`);
    }

    const data = await res.json();
    const text = data?.content?.[0]?.text || "{}";
    let parsed;
    try {
      parsed = JSON.parse(text);
    } catch {
      const start = text.indexOf("{");
      const end = text.lastIndexOf("}");
      if (start >= 0 && end > start) parsed = JSON.parse(text.slice(start, end + 1));
      else throw new Error("Claude response was not valid JSON");
    }
    if (!Array.isArray(parsed.tabsToClose)) parsed.tabsToClose = [];
    if (!Array.isArray(parsed.tabGroups)) parsed.tabGroups = [];
    return parsed;
  } catch (e) {
    console.error("analyzeTabsWithClaude error:", e);
    return {
      tabsToClose: [],
      tabGroups: [{ name: "All Tabs", color: "purple", tabIds: tabData.map((t) => t.id) }],
      reasoning: "Claude error - basic grouping applied",
    };
  }
}

/**
 * Router to selected provider/model
 */
async function analyzeTabs(tabData, { provider, model, importanceThreshold, keys }) {
  const prov = (provider || "openai").toLowerCase();
  if (prov === "gemini") {
    return analyzeTabsWithGemini(tabData, { geminiKey: keys?.geminiKey, importanceThreshold });
  }
  if (prov === "claude") {
    return analyzeTabsWithClaude(tabData, {
      claudeKey: keys?.claudeKey,
      model,
      importanceThreshold,
    });
  }
  // default OpenAI
  return analyzeTabsWithOpenAI(tabData, {
    apiKey: keys?.apiKey,
    model: model || "gpt-4.1",
    importanceThreshold,
  });
}

/**
 * Generic organizer used by auto-organize (uses router)
 */
async function organizeTabsGeneric({ provider, model, keys, importanceThreshold, autoClose }) {
  if (isProcessing) return;
  isProcessing = true;
  sendProgress("start");

  try {
    const tabs = await chrome.tabs.query({});
    sendProgress("tabs_collected", { total: tabs.length });

    const tabData = [];
    for (let i = 0; i < tabs.length; i++) {
      const t = tabs[i];
      let content = {};
      try {
        content = await extractTabContent(t);
      } catch (_e) {}
      tabData.push({
        id: t.id,
        url: t.url,
        title: t.title,
        content,
        favIconUrl: t.favIconUrl,
      });
      sendProgress("extract_progress", {
        completed: i + 1,
        total: tabs.length,
        tab: { id: t.id, title: t.title, url: t.url },
      });
    }

    sendProgress("ai_request", { totalTabs: tabData.length });
    const analysis = await analyzeTabs(tabData, {
      provider,
      model,
      importanceThreshold,
      keys,
    });
    sendProgress("ai_response", {
      tabsToClose: Array.isArray(analysis.tabsToClose) ? analysis.tabsToClose.length : 0,
      groups: Array.isArray(analysis.tabGroups) ? analysis.tabGroups.length : 0,
      reasoning: typeof analysis.reasoning === "string" ? analysis.reasoning.slice(0, 300) : "",
    });

    const idToTab = new Map();
    tabs.forEach((t) => idToTab.set(t.id, t));
    const closedTabsMeta = [];

    // Protection for auto flow
    const protectActive = new Set(tabs.filter((t) => t && t.active).map((t) => t.id));
    const nowTs = Date.now();
    if (Array.isArray(analysis.tabsToClose)) {
      analysis.tabsToClose = analysis.tabsToClose.filter((tid) => {
        const original = idToTab.get(tid);
        if (!original) return false;
        const url = original.url || "";
        if (protectActive.has(tid)) return false;
        if (url.startsWith("chrome://") || url.startsWith("chrome-extension://") || url === "about:blank" || url.includes("newtab")) return false;
        const touched = recentTouch.get(tid);
        if (touched && nowTs - touched < 30000) return false;
        return true;
      });
    }

    if (autoClose && Array.isArray(analysis.tabsToClose)) {
      let closed = 0;
      for (const tabId of analysis.tabsToClose) {
        try {
          const original = idToTab.get(tabId);
          if (original && original.url) {
            closedTabsMeta.push({
              url: original.url,
              windowId: original.windowId,
              index: original.index,
              active: !!original.active,
              pinned: !!original.pinned,
            });
          }
          await chrome.tabs.remove(tabId);
          closed++;
          sendProgress("closing_progress", { closed, total: analysis.tabsToClose.length, tabId });
        } catch (_e) {}
      }
      sendProgress("closing_done", { closed });
    }

    const groupedTabIds = [];
    if (Array.isArray(analysis.tabGroups) && analysis.tabGroups.length) {
      let grouped = 0;
      for (const group of analysis.tabGroups) {
        try {
          if (!Array.isArray(group.tabIds) || !group.tabIds.length) continue;
          const gid = await chrome.tabs.group({ tabIds: group.tabIds });
          await chrome.tabGroups.update(gid, {
            title: group.name,
            color: group.color || "purple",
          });
          grouped++;
          groupedTabIds.push([...group.tabIds]);
          sendProgress("group_progress", {
            grouped,
            total: analysis.tabGroups.length,
            name: group.name,
            count: group.tabIds?.length ?? 0,
          });
        } catch (_e) {}
      }
      sendProgress("grouping_done", { groupsCreated: grouped });
    }

    await setLastAction({
      type: autoClose ? (groupedTabIds.length ? "organize" : "close") : (groupedTabIds.length ? "group" : "none"),
      closedTabs: closedTabsMeta,
      groupedTabIds,
    });

    sendProgress("complete", { success: true });
  } catch (e) {
    console.error("organizeTabsGeneric error:", e);
    sendProgress("error", { message: String(e?.message || e) });
  } finally {
    isProcessing = false;
  }
}

async function getApiKeyOrThrow() {
  const { apiKey } = await chrome.storage.sync.get(["apiKey"]);
  if (!apiKey || typeof apiKey !== "string" || !apiKey.trim()) {
    throw new Error(
      "Missing OpenAI API key. Open the extension Options page and save your API key."
    );
  }
  return apiKey.trim();
}

// Main function to organize tabs and close unimportant ones
async function organizeTabsAndClose(settings) {
  if (isProcessing) {
    console.log("Already processing tabs...");
    return;
  }

  isProcessing = true;
  sendProgress("start");
  try {
    const storedKeys = await chrome.storage.sync.get([
      "apiKey",
      "geminiKey",
      "claudeKey",
      "providerAnalyze",
      "modelAnalyze",
    ]);
    const provider = (storedKeys.providerAnalyze || "openai").toLowerCase();
    const model =
      storedKeys.modelAnalyze ||
      (provider === "gemini"
        ? "gemini-2.5-flash-lite"
        : provider === "openai"
        ? "gpt-4.1"
        : "claude-3-5-sonnet-latest");

    // Load user prefs (allow overrides from settings)
    const stored = await chrome.storage.sync.get([
      "importanceThreshold",
      "autoClose",
    ]);

    const importanceThreshold =
      typeof settings.importanceThreshold === "number"
        ? settings.importanceThreshold
        : stored.importanceThreshold ?? 5;

    const autoClose =
      typeof settings.autoClose === "boolean"
        ? settings.autoClose
        : stored.autoClose ?? false;

    // Get all tabs
    const tabs = await chrome.tabs.query({});
    sendProgress("tabs_collected", { total: tabs.length });

    // Extract content from each tab
    const tabData = [];
    for (let i = 0; i < tabs.length; i++) {
      const tab = tabs[i];
      let content = {};
      try {
        content = await extractTabContent(tab);
      } catch (error) {
        console.warn(`Content extraction failed for tab ${tab.id}`, error);
      }
      tabData.push({
        id: tab.id,
        url: tab.url,
        title: tab.title,
        content,
        favIconUrl: tab.favIconUrl,
      });

      sendProgress("extract_progress", {
        completed: i + 1,
        total: tabs.length,
        tab: { id: tab.id, title: tab.title, url: tab.url },
      });
    }

    // Analyze with AI
    sendProgress("ai_request", { totalTabs: tabData.length });
    const analysis = await analyzeTabs(tabData, {
      provider,
      model,
      importanceThreshold,
      keys: {
        apiKey: storedKeys.apiKey,
        geminiKey: storedKeys.geminiKey,
        claudeKey: storedKeys.claudeKey,
      },
    });
    sendProgress("ai_response", {
      tabsToClose: Array.isArray(analysis.tabsToClose)
        ? analysis.tabsToClose.length
        : 0,
      groups: Array.isArray(analysis.tabGroups) ? analysis.tabGroups.length : 0,
      reasoning:
        typeof analysis.reasoning === "string"
          ? analysis.reasoning.slice(0, 300)
          : "",
    });

    // Prepare for Undo
    const idToTab = new Map();
    tabs.forEach((t) => idToTab.set(t.id, t));
    const closedTabsMeta = [];

    // Close tabs with low importance
    if (autoClose && Array.isArray(analysis.tabsToClose)) {
      let closed = 0;
      for (const tabId of analysis.tabsToClose) {
        try {
          const original = idToTab.get(tabId);
          if (original && original.url) {
            closedTabsMeta.push({
              url: original.url,
              windowId: original.windowId,
              index: original.index,
              active: !!original.active,
              pinned: !!original.pinned,
            });
          }
          await chrome.tabs.remove(tabId);
          closed++;
          sendProgress("closing_progress", {
            closed,
            total: analysis.tabsToClose.length,
            tabId,
          });
        } catch (error) {
          console.warn(`Failed to close tab ${tabId}:`, error);
        }
      }
      sendProgress("closing_done", { closed });
    }

    // Organize remaining tabs into groups
    const groupedTabIds = [];
    if (Array.isArray(analysis.tabGroups) && analysis.tabGroups.length) {
      let grouped = 0;
      for (const group of analysis.tabGroups) {
        try {
          if (!Array.isArray(group.tabIds) || group.tabIds.length === 0) {
            continue;
          }
          const createdGroupId = await chrome.tabs.group({
            tabIds: group.tabIds,
          });
          await chrome.tabGroups.update(createdGroupId, {
            title: group.name,
            color: group.color || "purple",
          });
          grouped++;
          groupedTabIds.push([...group.tabIds]);
          sendProgress("group_progress", {
            grouped,
            total: analysis.tabGroups.length,
            name: group.name,
            count: group.tabIds?.length ?? 0,
          });
        } catch (error) {
          console.warn(`Failed to create/update group ${group.name}:`, error);
        }
      }
      sendProgress("grouping_done", { groupsCreated: grouped });
    }

    // Persist last action for Undo
    await setLastAction({
      type: autoClose
        ? (groupedTabIds.length ? "organize" : "close")
        : (groupedTabIds.length ? "group" : "none"),
      closedTabs: closedTabsMeta,
      groupedTabIds,
    });

    sendProgress("complete", { success: true });
  } catch (error) {
    console.error("Error organizing tabs:", error);
    sendProgress("error", { message: String(error?.message || error) });
  } finally {
    isProcessing = false;
  }
}

// Close only low-importance tabs using AI (no grouping)
async function closeLowImportance(settings) {
  if (isProcessing) {
    console.log("Already processing tabs...");
    return;
  }

  isProcessing = true;
  sendProgress("start");
  try {
    const storedKeys = await chrome.storage.sync.get([
      "apiKey",
      "geminiKey",
      "claudeKey",
      "providerClose",
      "modelClose",
    ]);
    const provider = (storedKeys.providerClose || "openai").toLowerCase();
    const model =
      storedKeys.modelClose ||
      (provider === "gemini"
        ? "gemini-2.5-flash-lite"
        : provider === "openai"
        ? "gpt-4.1"
        : "claude-3-5-sonnet-latest");

    // Load threshold from storage or settings
    const stored = await chrome.storage.sync.get(["importanceThreshold"]);
    const importanceThreshold =
      typeof settings.importanceThreshold === "number"
        ? settings.importanceThreshold
        : stored.importanceThreshold ?? 5;

    // Get all tabs
    const tabs = await chrome.tabs.query({});
    sendProgress("tabs_collected", { total: tabs.length });

    // Extract content
    const tabData = [];
    for (let i = 0; i < tabs.length; i++) {
      const tab = tabs[i];
      let content = {};
      try {
        content = await extractTabContent(tab);
      } catch (error) {
        console.warn(`Content extraction failed for tab ${tab.id}`, error);
      }
      tabData.push({
        id: tab.id,
        url: tab.url,
        title: tab.title,
        content,
        favIconUrl: tab.favIconUrl,
      });

      sendProgress("extract_progress", {
        completed: i + 1,
        total: tabs.length,
        tab: { id: tab.id, title: tab.title, url: tab.url },
      });
    }

    // Analyze with AI
    sendProgress("ai_request", { totalTabs: tabData.length });
    const analysis = await analyzeTabs(tabData, {
      provider,
      model,
      importanceThreshold,
      keys: {
        apiKey: storedKeys.apiKey,
        geminiKey: storedKeys.geminiKey,
        claudeKey: storedKeys.claudeKey,
      },
    });
    sendProgress("ai_response", {
      tabsToClose: Array.isArray(analysis.tabsToClose)
        ? analysis.tabsToClose.length
        : 0,
      groups: 0,
      reasoning:
        typeof analysis.reasoning === "string"
          ? analysis.reasoning.slice(0, 300)
          : "",
    });

    // Prepare for Undo
    const idToTab = new Map();
    tabs.forEach((t) => idToTab.set(t.id, t));
    const closedTabsMeta = [];

    // Close tabs only (no grouping)
    if (Array.isArray(analysis.tabsToClose)) {
      let closed = 0;
      for (const tabId of analysis.tabsToClose) {
        try {
          const original = idToTab.get(tabId);
          if (original && original.url) {
            closedTabsMeta.push({
              url: original.url,
              windowId: original.windowId,
              index: original.index,
              active: !!original.active,
              pinned: !!original.pinned,
            });
          }
          await chrome.tabs.remove(tabId);
          closed++;
          sendProgress("closing_progress", {
            closed,
            total: analysis.tabsToClose.length,
            tabId,
          });
        } catch (error) {
          console.warn(`Failed to close tab ${tabId}:`, error);
        }
      }
      sendProgress("closing_done", { closed });
    }

    // Persist last action for Undo
    await setLastAction({
      type: "close",
      closedTabs: closedTabsMeta,
      groupedTabIds: [],
    });

    sendProgress("complete", { success: true });
  } catch (error) {
    console.error("Error closing low-importance tabs:", error);
    sendProgress("error", { message: String(error?.message || error) });
  } finally {
    isProcessing = false;
  }
}

// Undo last action: reopen closed tabs and ungroup previously grouped tabs
async function undoLastAction() {
  if (isProcessing) {
    console.log("Busy - cannot undo right now.");
    return;
  }
  isProcessing = true;
  sendProgress("undo_start");

  try {
    const action = await getLastAction();
    if (!action || action.type === "none") {
      sendProgress("error", { message: "Nothing to undo." });
      isProcessing = false;
      return;
    }

    // Ungroup first (to avoid moving reopened tabs into groups unexpectedly)
    if (Array.isArray(action.groupedTabIds) && action.groupedTabIds.length) {
      let processed = 0;
      for (const tabIds of action.groupedTabIds) {
        try {
          // Attempt to ungroup the tab IDs that still exist
          await chrome.tabs.ungroup(tabIds);
          processed++;
          sendProgress("undo_grouping_progress", {
            processed,
            total: action.groupedTabIds.length,
          });
        } catch (e) {
          // some IDs may no longer exist, ignore
          processed++;
        }
      }
      sendProgress("undo_grouping_done", { processed });
    }

    // Reopen closed tabs (best-effort restore of window/index)
    if (Array.isArray(action.closedTabs) && action.closedTabs.length) {
      let reopened = 0;
      for (const meta of action.closedTabs) {
        try {
          // Create tab in target window if possible
          const created = await chrome.tabs.create({
            url: meta.url,
            active: false, // avoid focus storm
            windowId: meta.windowId,
          });
          // Move to original index if valid
          if (typeof meta.index === "number" && meta.index >= 0) {
            try {
              await chrome.tabs.move(created.id, { index: meta.index, windowId: created.windowId });
            } catch (_e) {
              // ignore move errors
            }
          }
          // Repin if originally pinned
          if (meta.pinned) {
            try {
              await chrome.tabs.update(created.id, { pinned: true });
            } catch (_e) {
              // ignore
            }
          }
          reopened++;
          sendProgress("undo_reopen_progress", {
            reopened,
            total: action.closedTabs.length,
          });
        } catch (e) {
          // window may be gone or other error; try opening in current window
          try {
            const created = await chrome.tabs.create({ url: meta.url, active: false });
            reopened++;
            sendProgress("undo_reopen_progress", {
              reopened,
              total: action.closedTabs.length,
            });
          } catch (_e) {
            // give up on this tab
          }
        }
      }
      sendProgress("undo_reopen_done", { reopened });
    }

    await clearLastAction();
    sendProgress("undo_complete", { success: true });
  } catch (e) {
    console.error("Undo failed:", e);
    sendProgress("error", { message: "Undo failed: " + String(e?.message || e) });
  } finally {
    isProcessing = false;
  }
}

// Extract content from a tab
async function extractTabContent(tab) {
  const url = tab.url || "";
  if (url.startsWith("chrome://") || url.startsWith("chrome-extension://")) {
    return { note: "Chrome internal page" };
  }

  try {
    const results = await chrome.scripting.executeScript({
      target: { tabId: tab.id },
      func: () => {
        try {
          const description =
            document.querySelector('meta[name="description"]')?.content || "";
          const keywords =
            document.querySelector('meta[name="keywords"]')?.content || "";
          const headings = Array.from(
            document.querySelectorAll("h1, h2, h3")
          )
            .map((h) => h.textContent?.trim())
            .filter(Boolean)
            .slice(0, 10);
          const text =
            document.body?.innerText?.trim().slice(0, 2000) || "";

          return { description, keywords, headings, text };
        } catch (e) {
          return { error: "Extraction script error" };
        }
      },
    });

    return results?.[0]?.result || {};
  } catch (error) {
    console.error(`Failed to extract content from tab ${tab.id}:`, error);
    return {};
  }
}

// Analyze tabs with OpenAI GPT-4.1
async function analyzeTabsWithAI(tabData, { apiKey, importanceThreshold }) {
  const prompt = `You are an AI that organizes browser tabs. Analyze the following ${
    tabData.length
  } tabs and:
1) Rate each tab's importance from 1-10 based on content relevance, value, recency, professional/personal importance, uniqueness.
2) Suggest closing tabs with importance < ${importanceThreshold}.
3) Group remaining tabs into logical categories (max 8 groups). Use Chrome tab group colors: "blue","red","yellow","green","pink","purple","cyan","orange".

Tabs:
${tabData
  .map(
    (t, i) =>
      `Tab ${i + 1}:
- id: ${t.id}
- title: ${t.title}
- url: ${t.url}
- content: ${JSON.stringify(t.content).slice(0, 300)}...`
  )
  .join("\n")}

Respond ONLY with minified JSON of this shape (no markdown, no extra text):
{"tabsToClose":[tabId,...],"tabGroups":[{"name":"Group Name","color":"purple","tabIds":[ids...]}],"reasoning":"short string"}`;

  try {
    const res = await fetch("https://api.openai.com/v1/chat/completions", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${apiKey}`,
      },
      body: JSON.stringify({
        model: "gpt-4.1",
        messages: [{ role: "user", content: prompt }],
        temperature: 0.3,
        max_tokens: 900,
      }),
    });

    if (!res.ok) {
      const errText = await res.text().catch(() => "");
      throw new Error(`OpenAI API error: ${res.status} ${errText}`);
    }

    const data = await res.json();
    const content = data?.choices?.[0]?.message?.content || "{}";

    // Try to parse JSON from the model output
    let parsed;
    try {
      parsed = JSON.parse(content);
    } catch {
      // Attempt to extract JSON substring
      const start = content.indexOf("{");
      const end = content.lastIndexOf("}");
      if (start >= 0 && end > start) {
        parsed = JSON.parse(content.slice(start, end + 1));
      } else {
        throw new Error("Model response was not valid JSON");
      }
    }

    // Sanity checks
    if (!Array.isArray(parsed.tabsToClose)) parsed.tabsToClose = [];
    if (!Array.isArray(parsed.tabGroups)) parsed.tabGroups = [];

    return parsed;
  } catch (error) {
    console.error("Error calling OpenAI API:", error);
    // Fallback: single group with all tabs
    return {
      tabsToClose: [],
      tabGroups: [
        {
          name: "All Tabs",
          color: "purple",
          tabIds: tabData.map((t) => t.id),
        },
      ],
      reasoning: "API error - basic grouping applied",
    };
  }
}

// Debug: create random tabs
async function createDebugTabs() {
  const debugUrls = [
    "https://www.wikipedia.org",
    "https://www.github.com",
    "https://stackoverflow.com",
    "https://www.reddit.com",
    "https://www.youtube.com",
    "https://www.google.com/search?q=javascript",
    "https://www.amazon.com",
    "https://twitter.com",
    "https://www.linkedin.com",
    "https://news.ycombinator.com",
  ];

  const shuffled = debugUrls.sort(() => 0.5 - Math.random());
  const selectedCount = Math.floor(Math.random() * 8) + 18; // open 18-25 tabs
  const selectedUrls = shuffled.slice(0, selectedCount);

  for (const url of selectedUrls) {
    try {
      await chrome.tabs.create({ url, active: false });
    } catch (error) {
      console.warn(`Failed to create tab for ${url}:`, error);
    }
  }
}

// Debug: close all tabs except current
async function debugCloseAllTabs() {
  try {
    const tabs = await chrome.tabs.query({});
    const current = await chrome.tabs.query({ active: true, currentWindow: true });
    const currentId = current?.[0]?.id;
    const toClose = tabs.filter((t) => t.id !== currentId).map((t) => t.id);

    // Prepare lastAction
    const closedTabsMeta = tabs
      .filter((t) => t.id !== currentId && t.url)
      .map((t) => ({
        url: t.url,
        windowId: t.windowId,
        index: t.index,
        active: !!t.active,
        pinned: !!t.pinned,
      }));

    if (toClose.length) await chrome.tabs.remove(toClose);
    await setLastAction({ type: "close", closedTabs: closedTabsMeta, groupedTabIds: [] });
  } catch (error) {
    console.error("Error closing tabs:", error);
  }
}
