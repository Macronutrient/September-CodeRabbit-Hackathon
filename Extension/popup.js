// AI Tab Organizer - Popup (Modern dark UI + Live progress)
// - API key is managed in options page (options.html)
// - This popup loads/saves threshold/autoClose and shows progress during organization

document.addEventListener('DOMContentLoaded', () => {
  // Elements
  const el = (id) => document.getElementById(id);

  const tabCountEl = el('tabCount');

  const progressCard = el('progressCard');
  const progressFill = el('progressFill');
  const stageText = el('stageText');
  const percentText = el('percentText');
  const progressLog = el('progressLog');
  const statusMsg = el('statusMsg');

  const thresholdSlider = el('threshold');
  const thresholdValue = el('thresholdValue');
  const autoCloseChk = el('autoClose');
  const autoOrganizeEl = el('autoOrganize');

  const openOptions = el('openOptions');

  const createTabsBtn = el('createTabsBtn');
  const closeLowBtn = el('closeLowBtn');
  const undoBtn = el('undoBtn');
  const versionInfo = el('versionInfo');
  const closeAllBtn = el('closeAllBtn'); // may be null (button removed from UI)
  const organizeBtn = el('organizeBtn');

  // State for progress calculation
  const PCT_WEIGHTS = {
    extract: 0.50,   // 50%
    ai: 0.10,        // 10%
    closing: 0.20,   // 20%
    grouping: 0.20,  // 20%
  };
  const prog = {
    totalTabs: 0,
    extracted: 0,
    aiStarted: false,
    aiDone: false,
    closingTotal: 0,
    closingDone: 0,
    groupingTotal: 0,
    groupingDone: 0,
    running: false,
  };

  function setRunning(isRunning) {
    prog.running = isRunning;
    organizeBtn.classList.toggle('disabled', isRunning);
    createTabsBtn.classList.toggle('disabled', isRunning);
    closeLowBtn?.classList.toggle('disabled', isRunning);
    undoBtn?.classList.toggle('disabled', isRunning);
    if (closeAllBtn) closeAllBtn.classList.toggle('disabled', isRunning);

    if (isRunning) {
      progressCard.style.display = '';
      stageText.textContent = 'Preparing…';
      setPercent(0);
      progressLog.innerHTML = '';
      statusMsg.style.display = 'none';
      logLine('Started.');
    } else {
      logLine('Idle.');
    }
  }

  function setPercent(p) {
    const clamped = Math.max(0, Math.min(100, Math.round(p)));
    progressFill.style.width = `${clamped}%`;
    percentText.textContent = `${clamped}%`;
  }

  function logLine(text) {
    const div = document.createElement('div');
    div.className = 'item';
    const now = new Date();
    const ts = now.toLocaleTimeString([], {hour: '2-digit', minute:'2-digit', second:'2-digit'});
    div.textContent = `[${ts}] ${text}`;
    progressLog.appendChild(div);
    progressLog.scrollTop = progressLog.scrollHeight;
  }

  function computePercent() {
    // Extraction progress
    const extractPct = prog.totalTabs > 0 ? (prog.extracted / prog.totalTabs) : 0;

    // AI progress: 0 until started, 1 when done
    let aiPct = 0;
    if (prog.aiStarted && !prog.aiDone) aiPct = 0.5;
    if (prog.aiDone) aiPct = 1;

    // Closing progress
    const closingPct = prog.closingTotal > 0 ? (prog.closingDone / prog.closingTotal) : (prog.closingTotal === 0 ? 1 : 0);

    // Grouping progress
    const groupingPct = prog.groupingTotal > 0 ? (prog.groupingDone / prog.groupingTotal) : (prog.groupingTotal === 0 ? 1 : 0);

    const total =
      extractPct * PCT_WEIGHTS.extract +
      aiPct * PCT_WEIGHTS.ai +
      closingPct * PCT_WEIGHTS.closing +
      groupingPct * PCT_WEIGHTS.grouping;

    return total * 100;
  }

  function updatePercentAndStage(stage) {
    if (stage) stageText.textContent = stage;
    setPercent(computePercent());
  }

  // Settings load/save
  async function loadSettings() {
    try {
      const data = await chrome.storage.sync.get(['importanceThreshold', 'autoClose', 'autoOrganize']);
      const threshold = typeof data.importanceThreshold === 'number' ? data.importanceThreshold : 5;
      const autoClose = !!data.autoClose;

      thresholdSlider.value = String(threshold);
      thresholdValue.textContent = String(threshold);
      autoCloseChk.checked = autoClose;
      autoOrganizeEl.checked = !!data.autoOrganize;
    } catch (e) {
      console.error('Failed to load settings:', e);
    }
  }

  async function saveSettings() {
    const importanceThreshold = parseInt(thresholdSlider.value, 10) || 5;
    const autoClose = !!autoCloseChk.checked;
    const autoOrganize = !!autoOrganizeEl.checked;
    await chrome.storage.sync.set({ importanceThreshold, autoClose, autoOrganize });
  }

  // Tab count
  async function refreshTabCount() {
    try {
      const resp = await chrome.runtime.sendMessage({ action: 'getTabCount' });
      if (resp && typeof resp.count === 'number') {
        tabCountEl.textContent = `${resp.count} tabs`;
      }
    } catch (e) {
      // ignore
    }
  }

  // Open options
  openOptions?.addEventListener('click', (e) => {
    e.preventDefault();
    if (chrome.runtime.openOptionsPage) {
      chrome.runtime.openOptionsPage();
    } else {
      window.open('options.html');
    }
  });

  // Controls
  thresholdSlider.addEventListener('input', () => {
    thresholdValue.textContent = thresholdSlider.value;
  });
  thresholdSlider.addEventListener('change', saveSettings);
  autoCloseChk.addEventListener('change', saveSettings);
  autoOrganizeEl.addEventListener('change', saveSettings);

  // Make the entire row clickable to toggle switches
  const toggleRows = document.querySelectorAll('[data-toggle-for]');
  toggleRows.forEach((row) => {
    row.addEventListener('click', (e) => {
      // Ignore direct clicks on actual inputs to prevent double toggle
      if (e.target && (e.target.tagName || '').toLowerCase() === 'input') return;
      const id = row.getAttribute('data-toggle-for');
      const checkbox = document.getElementById(id);
      if (!checkbox) return;
      checkbox.checked = !checkbox.checked;
      saveSettings();
    }, { passive: true });
  });

  // Buttons
  createTabsBtn.addEventListener('click', async () => {
    createTabsBtn.classList.add('disabled');
    try {
      await chrome.runtime.sendMessage({ action: 'debugCreateTabs' });
      setTimeout(refreshTabCount, 800);
    } finally {
      createTabsBtn.classList.remove('disabled');
    }
  });

  // Close Low-Importance using AI scores
  closeLowBtn?.addEventListener('click', async () => {
    setRunning(true);
    // Reset state for progress
    prog.totalTabs = 0;
    prog.extracted = 0;
    prog.aiStarted = false;
    prog.aiDone = false;
    prog.closingTotal = 0;
    prog.closingDone = 0;
    prog.groupingTotal = 0; // not used here, but keep model consistent
    prog.groupingDone = 0;

    const settings = {
      importanceThreshold: parseInt(thresholdSlider.value, 10) || 5
    };

    try {
      await chrome.runtime.sendMessage({
        action: 'closeLowImportance',
        settings,
      });
      logLine('Requested close of low-importance tabs…');
    } catch (e) {
      logLine('Failed to close low-importance tabs.');
      setRunning(false);
    }
  });

  // Undo last action
  undoBtn?.addEventListener('click', async () => {
    setRunning(true);
    try {
      await chrome.runtime.sendMessage({ action: 'undoLastAction' });
      logLine('Requested undo…');
    } catch (e) {
      logLine('Failed to undo.');
      setRunning(false);
    }
  });

  // Legacy Close All (button removed from UI) - keep optional guard for compatibility
  closeAllBtn?.addEventListener('click', async () => {
    if (!confirm('Close ALL tabs (except this one)?')) return;
    closeAllBtn.classList.add('disabled');
    try {
      await chrome.runtime.sendMessage({ action: 'debugCloseAllTabs' });
      setTimeout(refreshTabCount, 800);
    } finally {
      closeAllBtn.classList.remove('disabled');
    }
  });

  organizeBtn.addEventListener('click', async () => {
    setRunning(true);
    // Reset state
    prog.totalTabs = 0;
    prog.extracted = 0;
    prog.aiStarted = false;
    prog.aiDone = false;
    prog.closingTotal = 0;
    prog.closingDone = 0;
    prog.groupingTotal = 0;
    prog.groupingDone = 0;

    // Send message to background to start
    const settings = {
      importanceThreshold: parseInt(thresholdSlider.value, 10) || 5,
      autoClose: !!autoCloseChk.checked,
    };

    try {
      await chrome.runtime.sendMessage({
        action: 'organizeTabsAndClose',
        settings,
      });
      logLine('Requested organization…');
    } catch (e) {
      logLine('Failed to start organization.');
      setRunning(false);
    }
  });

  // Reveal hidden "Create Test Tabs" after clicking version 5 times
  let versionClicks = 0;
  versionInfo?.addEventListener('click', () => {
    versionClicks++;
    if (versionClicks >= 5) {
      createTabsBtn?.classList.toggle('hidden');
      versionClicks = 0;
    }
  });

  // Keyboard shortcuts
  document.addEventListener('keydown', (e) => {
    if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
      e.preventDefault();
      if (!prog.running) organizeBtn.click();
    }
  });

  // Listen for progress events from background
  chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
    if (!msg || msg.type !== 'progress') return;

    switch (msg.stage) {
      case 'start':
        logLine('Starting…');
        updatePercentAndStage('Preparing…');
        break;

      case 'tabs_collected':
        prog.totalTabs = msg.total || 0;
        logLine(`Collected ${prog.totalTabs} tabs.`);
        updatePercentAndStage('Collecting tabs…');
        break;

      case 'extract_progress':
        prog.extracted = msg.completed || prog.extracted;
        updatePercentAndStage(`Extracting content (${prog.extracted}/${prog.totalTabs})`);
        if (msg.tab?.title) {
          logLine(`Extracted: ${truncate(msg.tab.title, 60)}`);
        }
        break;

      case 'ai_request':
        prog.aiStarted = true;
        updatePercentAndStage('Analyzing with GPT-4.1…');
        logLine('Sending tabs to AI…');
        break;

      case 'ai_response':
        prog.aiDone = true;
        if (typeof msg.reasoning === 'string' && msg.reasoning.length) {
          logLine(`AI reasoning: ${truncate(msg.reasoning, 200)}`);
        } else {
          logLine('AI analysis complete.');
        }
        updatePercentAndStage('AI analysis complete');
        // Initialize totals for closing/grouping so percent calc knows them
        if (typeof msg.tabsToClose === 'number') prog.closingTotal = msg.tabsToClose;
        if (typeof msg.groups === 'number') prog.groupingTotal = msg.groups;
        break;

      case 'closing_progress':
        prog.closingTotal = Math.max(prog.closingTotal, msg.total || 0);
        prog.closingDone = msg.closed || prog.closingDone;
        updatePercentAndStage(`Closing tabs (${prog.closingDone}/${prog.closingTotal})`);
        break;

      case 'closing_done':
        logLine(`Closed ${msg.closed || 0} tabs.`);
        updatePercentAndStage('Closing complete');
        break;

      case 'group_progress':
        prog.groupingTotal = Math.max(prog.groupingTotal, msg.total || 0);
        prog.groupingDone = msg.grouped || prog.groupingDone;
        updatePercentAndStage(`Grouping tabs (${prog.groupingDone}/${prog.groupingTotal})`);
        if (msg.name) {
          logLine(`Created group: ${msg.name} (${msg.count || 0} tabs)`);
        }
        break;

      case 'grouping_done':
        logLine(`Created ${msg.groupsCreated || 0} groups.`);
        updatePercentAndStage('Grouping complete');
        break;

      case 'complete':
        updatePercentAndStage('All done!');
        setPercent(100);
        statusMsg.style.display = '';
        statusMsg.textContent = 'Completed successfully.';
        setRunning(false);
        setTimeout(refreshTabCount, 800);
        break;

      case 'error':
        statusMsg.style.display = '';
        statusMsg.textContent = msg.message || 'An error occurred.';
        logLine(`Error: ${msg.message || 'Unknown error'}`);
        setRunning(false);
        break;

      case 'undo_start':
        logLine('Undo started…');
        stageText.textContent = 'Undoing…';
        setPercent(5);
        break;

      case 'undo_grouping_progress': {
        const processed = msg.processed || 0;
        const total = msg.total || 0;
        stageText.textContent = `Ungrouping (${processed}/${total})`;
        if (total > 0) setPercent(20 + Math.round((processed / total) * 20));
        break;
      }

      case 'undo_grouping_done':
        logLine('Ungrouping complete.');
        stageText.textContent = 'Ungrouping complete';
        setPercent(40);
        break;

      case 'undo_reopen_progress': {
        const reopened = msg.reopened || 0;
        const total = msg.total || 0;
        stageText.textContent = `Reopening tabs (${reopened}/${total})`;
        if (total > 0) setPercent(50 + Math.round((reopened / total) * 45));
        break;
      }

      case 'undo_reopen_done':
        logLine('Reopen complete.');
        stageText.textContent = 'Reopen complete';
        break;

      case 'undo_complete':
        updatePercentAndStage('Undo complete');
        setPercent(100);
        statusMsg.style.display = '';
        statusMsg.textContent = 'Undo completed successfully.';
        setRunning(false);
        setTimeout(refreshTabCount, 800);
        break;

      default:
        // no-op
        break;
    }
  });

  function truncate(s, n) {
    if (!s) return '';
    return s.length > n ? s.slice(0, n - 1) + '…' : s;
  }

  // Init
  loadSettings();
  refreshTabCount();
  // Keep tab count fresh
  setInterval(refreshTabCount, 3000);

  setPercent(0);
  progressCard.style.display = 'none'; // hidden until run
});
