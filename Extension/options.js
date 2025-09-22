// AI Tab Organizer - Options (API Keys + Provider/Model Management)
// Populates provider-specific model lists by calling each vendor's Models API
// and saves per-function provider/model choices (Analyze, Close, Auto).

(function () {
  const $ = (sel) => document.querySelector(sel);

  // Key inputs
  const apiKeyInput = $("#apiKey");        // OpenAI
  const geminiKeyInput = $("#geminiKey");  // Google Gemini
  const claudeKeyInput = $("#claudeKey");  // Anthropic Claude

  // Buttons
  const saveBtn = $("#saveBtn");
  const clearBtn = $("#clearBtn");
  const toggleKeyBtn = $("#toggleKey");
  const toggleGeminiBtn = $("#toggleGeminiKey");
  const toggleClaudeBtn = $("#toggleClaudeKey");

  // Provider selectors
  const providerAnalyze = $("#providerAnalyze");
  const providerClose = $("#providerClose");
  const providerAuto = $("#providerAuto");

  // Model selectors
  const modelAnalyze = $("#modelAnalyze");
  const modelClose = $("#modelClose");
  const modelAuto = $("#modelAuto");

  // Status
  const statusEl = $("#status");
  const statusDot = statusEl?.querySelector(".dot");
  const statusMsg = statusEl?.querySelector(".msg");

  function setStatus(type, msg) {
    if (!statusEl) return;
    statusEl.classList.remove("success", "warn", "error");
    if (type) statusEl.classList.add(type);
    if (statusDot) {
      // color driven by classes
    }
    if (statusMsg) statusMsg.textContent = msg || "";
  }

  function toggleVisibility(input, btn) {
    const isPwd = input.type === "password";
    input.type = isPwd ? "text" : "password";
    if (btn) btn.textContent = isPwd ? "Hide" : "Show";
  }

  // Populate <select> utilities
  function populateSelect(select, items, selectedValue) {
    if (!select) return;
    // Preserve focus
    const current = selectedValue ?? select.value;
    // Remove all
    while (select.firstChild) select.removeChild(select.firstChild);

    // Add options
    (items || []).forEach(({ value, label }) => {
      const opt = document.createElement("option");
      opt.value = value;
      opt.textContent = label || value;
      select.appendChild(opt);
    });

    // Restore selection if exists
    const exists = Array.from(select.options).some((o) => o.value === current);
    if (exists) {
      select.value = current;
    } else if (select.options.length) {
      select.value = select.options[0].value;
    }
  }

  // ========= Fetch models from providers =========

  async function fetchOpenAIModels(openaiKey) {
    // GET https://api.openai.com/v1/models
    // Returns many; filter to chat-capable families (gpt, 4o, 4.1 etc.)
    try {
      if (!openaiKey) return [];
      const res = await fetch("https://api.openai.com/v1/models", {
        headers: { Authorization: `Bearer ${openaiKey}` },
      });
      if (!res.ok) throw new Error(await res.text().catch(() => res.statusText));
      const data = await res.json();
      const ids = (data?.data || [])
        .map((m) => m.id)
        .filter((id) => typeof id === "string")
        .filter((id) =>
          id.includes("gpt") ||
          id.includes("o-mini") ||
          id.includes("4.1") ||
          id.includes("4o") ||
          id.includes("gpt-4")
        )
        .sort();

      // Dedupe
      const uniq = [...new Set(ids)];
      return uniq.map((id) => ({ value: id, label: id }));
    } catch (e) {
      console.warn("OpenAI models fetch failed:", e);
      // Fallback curated list
      const fallback = ["gpt-4.1", "gpt-4o-mini"];
      return fallback.map((id) => ({ value: id, label: id }));
    }
  }

  async function fetchGeminiModels(geminiKey) {
    // GET https://generativelanguage.googleapis.com/v1beta/models?key=...
    try {
      if (!geminiKey) return [];
      const res = await fetch(
        "https://generativelanguage.googleapis.com/v1beta/models?key=" +
          encodeURIComponent(geminiKey)
      );
      if (!res.ok) throw new Error(await res.text().catch(() => res.statusText));
      const data = await res.json();
      const models = (data?.models || [])
        .map((m) => m.name)
        .filter((n) => typeof n === "string")
        .filter((n) => n.includes("gemini"))
        .sort();

      const uniq = [...new Set(models)];
      return uniq.map((id) => ({ value: id.replace(/^models\//, ""), label: id.replace(/^models\//, "") }));
    } catch (e) {
      console.warn("Gemini models fetch failed:", e);
      // Fallback curated list
      const fallback = ["gemini-2.5-flash-lite", "gemini-1.5-flash"];
      return fallback.map((id) => ({ value: id, label: id }));
    }
  }

  async function fetchClaudeModels(claudeKey) {
    // GET https://api.anthropic.com/v1/models
    // Headers: x-api-key, anthropic-version
    try {
      if (!claudeKey) return [];
      const res = await fetch("https://api.anthropic.com/v1/models", {
        headers: {
          "x-api-key": claudeKey,
          "anthropic-version": "2023-06-01",
        },
      });
      if (!res.ok) throw new Error(await res.text().catch(() => res.statusText));
      const data = await res.json();
      const ids = (data?.data || [])
        .map((m) => m.id || m.name)
        .filter((id) => typeof id === "string" && id.includes("claude"))
        .sort();
      const uniq = [...new Set(ids)];
      return uniq.map((id) => ({ value: id, label: id }));
    } catch (e) {
      console.warn("Claude models fetch failed:", e);
      const fallback = ["claude-3-5-sonnet-latest", "claude-3-haiku-20240307"];
      return fallback.map((id) => ({ value: id, label: id }));
    }
  }

  async function buildModelPickers() {
    setStatus("", "Loading models...");
    try {
      const { apiKey, geminiKey, claudeKey } = await chrome.storage.sync.get([
        "apiKey",
        "geminiKey",
        "claudeKey",
      ]);

      // Parallel fetches
      const [openaiModels, geminiModels, claudeModels] = await Promise.all([
        fetchOpenAIModels(apiKey),
        fetchGeminiModels(geminiKey),
        fetchClaudeModels(claudeKey),
      ]);

      // For provider changes, repopulate the matching model select
      const providerToList = {
        openai: openaiModels,
        gemini: geminiModels,
        claude: claudeModels,
      };

      function refreshModelSelect(providerSel, modelSel, savedModel) {
        const provider = providerSel?.value || "openai";
        const list = providerToList[provider] || [];
        populateSelect(modelSel, list, savedModel);
      }

      // Load any saved selections
      const {
        providerAnalyze: pa,
        modelAnalyze: ma,
        providerClose: pc,
        modelClose: mc,
        providerAuto: pauto,
        modelAuto: mauto,
      } = await chrome.storage.sync.get([
        "providerAnalyze",
        "modelAnalyze",
        "providerClose",
        "modelClose",
        "providerAuto",
        "modelAuto",
      ]);

      if (providerAnalyze) providerAnalyze.value = pa || "openai";
      if (providerClose) providerClose.value = pc || "openai";
      if (providerAuto) providerAuto.value = pauto || "gemini";

      refreshModelSelect(providerAnalyze, modelAnalyze, ma || "gpt-4.1");
      refreshModelSelect(providerClose, modelClose, mc || "gpt-4.1");
      refreshModelSelect(providerAuto, modelAuto, mauto || "gemini-2.5-flash-lite");

      // Provider change handlers
      providerAnalyze?.addEventListener("change", () => {
        refreshModelSelect(providerAnalyze, modelAnalyze);
        persistModels();
      });
      providerClose?.addEventListener("change", () => {
        refreshModelSelect(providerClose, modelClose);
        persistModels();
      });
      providerAuto?.addEventListener("change", () => {
        refreshModelSelect(providerAuto, modelAuto);
        persistModels();
      });

      // Model change handlers
      modelAnalyze?.addEventListener("change", persistModels);
      modelClose?.addEventListener("change", persistModels);
      modelAuto?.addEventListener("change", persistModels);

      setStatus("success", "Models loaded.");
    } catch (e) {
      console.error("buildModelPickers error:", e);
      setStatus("error", "Failed to load models.");
    }
  }

  async function persistModels() {
    try {
      const payload = {
        providerAnalyze: providerAnalyze?.value || "openai",
        modelAnalyze: modelAnalyze?.value || "gpt-4.1",
        providerClose: providerClose?.value || "openai",
        modelClose: modelClose?.value || "gpt-4.1",
        providerAuto: providerAuto?.value || "gemini",
        modelAuto: modelAuto?.value || "gemini-2.5-flash-lite",
      };
      await chrome.storage.sync.set(payload);
      setStatus("success", "Model selections saved.");
    } catch (e) {
      setStatus("error", "Failed to save model selections.");
    }
  }

  async function loadKeysAndModels() {
    try {
      const { apiKey, geminiKey, claudeKey } = await chrome.storage.sync.get([
        "apiKey",
        "geminiKey",
        "claudeKey",
      ]);
      if (apiKey) apiKeyInput.value = apiKey;
      if (geminiKey) geminiKeyInput.value = geminiKey;
      if (claudeKey) claudeKeyInput.value = claudeKey;

      await buildModelPickers();
    } catch (e) {
      console.error("loadKeysAndModels error:", e);
      setStatus("error", "Failed to load saved keys.");
    }
  }

  function isLikelyOpenAIKey(k) {
    return typeof k === "string" && k.trim().startsWith("sk-");
  }

  // Save keys
  async function saveKeys() {
    const openai = apiKeyInput.value.trim();
    const gemini = geminiKeyInput?.value?.trim() || "";
    const claude = claudeKeyInput?.value?.trim() || "";

    if (!openai && !gemini && !claude) {
      setStatus("warn", "Please enter at least one provider API key.");
      return;
    }
    if (openai && !isLikelyOpenAIKey(openai)) {
      setStatus("warn", 'OpenAI key should start with "sk-". Saving anyway.');
    }
    try {
      const payload = {};
      if (openai) payload.apiKey = openai;
      if (gemini) payload.geminiKey = gemini;
      if (claude) payload.claudeKey = claude;
      await chrome.storage.sync.set(payload);
      setStatus("success", "Keys saved. Fetching models...");
      await buildModelPickers();
    } catch (e) {
      console.error("Failed to save keys:", e);
      setStatus("error", "Failed to save keys.");
    }
  }

  // Clear keys
  async function clearKeys() {
    try {
      await chrome.storage.sync.remove([
        "apiKey",
        "geminiKey",
        "claudeKey",
      ]);
      apiKeyInput.value = "";
      if (geminiKeyInput) geminiKeyInput.value = "";
      if (claudeKeyInput) claudeKeyInput.value = "";
      setStatus("success", "Keys cleared.");
      // clear model picks too
      await chrome.storage.sync.remove([
        "providerAnalyze",
        "modelAnalyze",
        "providerClose",
        "modelClose",
        "providerAuto",
        "modelAuto",
      ]);
      // Rebuild lists (will fall back to curated)
      await buildModelPickers();
    } catch (e) {
      console.error("Failed to clear keys:", e);
      setStatus("error", "Failed to clear keys.");
    }
  }

  // Wire up events
  saveBtn?.addEventListener("click", saveKeys);
  clearBtn?.addEventListener("click", clearKeys);

  toggleKeyBtn?.addEventListener("click", () =>
    toggleVisibility(apiKeyInput, toggleKeyBtn)
  );
  toggleGeminiBtn?.addEventListener("click", () =>
    toggleVisibility(geminiKeyInput, toggleGeminiBtn)
  );
  toggleClaudeBtn?.addEventListener("click", () =>
    toggleVisibility(claudeKeyInput, toggleClaudeBtn)
  );

  // Light live feedback for OpenAI key
  apiKeyInput?.addEventListener("input", () => {
    const v = apiKeyInput.value.trim();
    if (!v) {
      setStatus("", "Waiting for changes…");
      return;
    }
    if (isLikelyOpenAIKey(v)) {
      setStatus("success", "OpenAI key looks valid.");
    } else {
      setStatus("warn", 'OpenAI key format may be invalid (expected prefix "sk-").');
    }
  });

  // Init
  loadKeysAndModels();
})();
