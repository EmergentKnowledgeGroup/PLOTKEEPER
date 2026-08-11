/* Plotkeeper's dashboard is intentionally dependency-free. The API adapter below
 * accepts the canonical fields and harmlessly tolerates partial responses while
 * keeping unverified states visible. */
(() => {
  'use strict';

  const state = { runs: [], run: null, contract: null, tasks: [], events: [], reports: [], sessions: [], selected: null, filter: '', selectionRequired: false };
  const $ = (selector, root = document) => root.querySelector(selector);
  const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];
  const text = (value, fallback = '—') => value === null || value === undefined || value === '' ? fallback : String(value);
  const number = (value) => { const n = Number(value); return Number.isFinite(n) ? n : null; };
  const slug = (value) => text(value, 'unknown').toLowerCase().replace(/\s+/g, '_').replace(/[^a-z0-9_-]/g, '');
  const statusLabel = (value) => text(value, 'Unknown').replace(/[_-]+/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
  const statusClass = (value) => `status-${slug(value)}`;
  const asArray = (value) => Array.isArray(value) ? value : [];
  const escape = (value) => text(value).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

  function normalizeRun(raw = {}) {
    return { ...raw,
      id: text(raw.run_id ?? raw.id ?? raw.runId, ''),
      title: text(raw.task_label ?? raw.title ?? raw.name ?? raw.project_name ?? raw.goal, 'Untitled run'),
      projectName: text(raw.project_name, 'Unknown project'),
      status: text(raw.status ?? raw.state, 'unknown'), progress: number(raw.progress ?? raw.progress_percent),
      currentTaskId: text(raw.current_task_id ?? raw.currentTaskId, ''), updatedAt: raw.updated_at ?? raw.updatedAt,
      reviewState: raw.review_state ?? raw.reviewState, rootSession: raw.bound_session_id ?? raw.session_id ?? raw.thread_id ?? raw.root_session_id ?? raw.rootSessionId,
      taskId: text(raw.task_id ?? raw.thread_id ?? raw.session_id ?? raw.root_session_id, ''),
    };
  }

  function normalizeTask(raw = {}, index = 0) {
    return { ...raw, id: text(raw.task_id ?? raw.id ?? raw.taskId, `task-${index + 1}`), title: text(raw.title ?? raw.name, 'Untitled task'),
      status: text(raw.status, 'unknown'), progress: number(raw.progress ?? raw.progress_percent), owner: text(raw.owner ?? raw.agent_path ?? raw.assignee, 'Unassigned'),
      parentId: text(raw.parent_task_id ?? raw.parentTaskId, ''), workstream: text(raw.workstream ?? raw.workstream_name ?? raw.phase ?? raw.stage, 'Unassigned work'),
      purpose: text(raw.purpose ?? raw.summary ?? raw.description, 'No purpose or summary attached.'), summary: text(raw.summary ?? raw.description ?? raw.purpose, 'No summary attached.'),
      evidence: asArray(raw.evidence), reports: asArray(raw.reports), preserve: asArray(raw.must_remain_true ?? raw.preserve),
    };
  }

  function setConnection(kind, label) { const node = $('#connection-status'); node.className = `connection ${kind ? `is-${kind}` : ''}`; node.innerHTML = `<span class="connection-dot" aria-hidden="true"></span><span>${escape(label)}</span>`; }
  function setRunHeader(run) {
    if (!run) return;
    $('#run-goal').textContent = run.title;
    const value = run.progress === null ? '—' : `${Math.max(0, Math.min(100, run.progress))}%`;
    $('#run-progress-value').textContent = value;
    $('#run-progress-bar').style.width = run.progress === null ? '0%' : `${Math.max(0, Math.min(100, run.progress))}%`;
    const state = $('#run-state'); state.className = `run-state ${statusClass(run.status)}`; state.textContent = statusLabel(run.status).toUpperCase();
    $('#working-meta').textContent = run.updatedAt ? `Updated ${formatDate(run.updatedAt)}` : `Run ${run.id || 'without an id'}`;
  }
  function renderContract(contract) {
    state.contract = contract;
    const payload = contract?.payload ?? contract;
    const badge = $('#contract-badge');
    if (!payload) {
      $('#contract-goal').textContent = 'No goal contract synced'; $('#contract-id').textContent = '—';
      $('#contract-baseline').textContent = '—'; $('#contract-invariants').innerHTML = '<li>No contract data available.</li>';
      badge.textContent = 'MISSING'; badge.className = 'run-state state-unknown'; return;
    }
    $('#contract-goal').textContent = text(payload.user_goal, 'Goal not recorded');
    $('#contract-id').textContent = text(payload.id ?? contract.contract_id);
    $('#contract-baseline').textContent = text(payload.baseline?.sha ?? contract.baseline_sha);
    const invariants = asArray(payload.invariants);
    $('#contract-invariants').innerHTML = (invariants.length ? invariants : ['No invariants recorded.']).map(item => `<li>${escape(item)}</li>`).join('');
    badge.textContent = statusLabel(payload.status ?? contract.status).toUpperCase(); badge.className = `run-state ${statusClass(payload.status ?? contract.status)}`;
  }
  function formatDate(value) { if (!value) return 'time unknown'; const date = new Date(value); return Number.isNaN(date.valueOf()) ? text(value) : date.toLocaleString([], { dateStyle: 'medium', timeStyle: 'short' }); }
  function formatProgress(value) { return value === null ? '—' : `${Math.max(0, Math.min(100, value))}%`; }

  async function getJson(url, options) {
    const response = await fetch(url, { headers: { Accept: 'application/json' }, ...options });
    if (!response.ok) throw new Error(`API ${response.status}`);
    return response.json();
  }

  function renderSelectionState(message) {
    state.selectionRequired = true; state.run = null; state.contract = null; state.tasks = []; state.events = []; state.reports = []; state.sessions = [];
    const selector = $('#run-selector');
    let placeholder = selector.querySelector('option[value=""]');
    if (!placeholder) { placeholder = document.createElement('option'); placeholder.value = ''; placeholder.textContent = 'Select an active run…'; placeholder.disabled = true; selector.prepend(placeholder); }
    selector.value = '';
    renderBoard([]); $('#board-message').hidden = false; $('#board-message').textContent = message;
    $('#run-goal').textContent = 'Select an active run'; $('#run-state').textContent = 'SELECTION REQUIRED'; $('#run-state').className = 'run-state state-unknown';
    $('#working-title').textContent = 'No run selected'; $('#working-meta').textContent = 'Plotkeeper will not guess between active tasks.'; $('#check-in').disabled = true;
    renderContract(null); clearDetail();
  }

  function renderRunSelector() {
    const selector = $('#run-selector'); selector.replaceChildren();
    const groups = new Map();
    state.runs.forEach(run => { const key = run.projectName || 'Unknown project'; if (!groups.has(key)) groups.set(key, []); groups.get(key).push(run); });
    groups.forEach((runs, project) => {
      const group = document.createElement('optgroup'); group.label = project;
      runs.forEach(run => { const option = document.createElement('option'); option.value = run.id; option.textContent = `${run.title} · ${run.taskId || run.id} · ${statusLabel(run.status)}`; group.appendChild(option); });
      selector.appendChild(group);
    });
    selector.disabled = !state.runs.length;
  }

  function boundLocator() {
    const params = new URLSearchParams(window.location.search);
    const runId = params.get('run_id'); const sessionId = params.get('session_id');
    return runId || sessionId ? { runId, sessionId } : null;
  }

  function setBoundUrl(run) {
    if (!run?.id) return;
    const params = new URLSearchParams(); params.set('run_id', run.id); if (run.rootSession) params.set('session_id', run.rootSession);
    window.history.replaceState({}, '', `${window.location.pathname}?${params.toString()}`);
  }

  async function loadRuns() {
    try {
      const payload = await getJson('/api/runs');
      state.runs = asArray(payload?.runs ?? payload).map(normalizeRun).filter(run => run.id);
      setConnection('online', `${state.runs.length} run${state.runs.length === 1 ? '' : 's'}`);
      renderRunSelector();
      const locator = boundLocator();
      if (locator) {
        const query = new URLSearchParams(); if (locator.runId) query.set('run_id', locator.runId); if (locator.sessionId) query.set('session_id', locator.sessionId);
        try {
          const resolved = await getJson(`/api/current?${query.toString()}`); const exact = normalizeRun(resolved?.run ?? resolved);
          if (!exact.id) throw new Error('locator did not resolve a run');
          if (!state.runs.some(run => run.id === exact.id)) state.runs.push(exact);
          renderRunSelector(); $('#run-selector').value = exact.id; await loadRun(exact.id); return;
        } catch (error) { renderSelectionState(`The requested run is unavailable (${error.message}). Choose an active run from the selector.`); return; }
      }
      if (state.runs.length === 1) { $('#run-selector').value = state.runs[0].id; setBoundUrl(state.runs[0]); await loadRun(state.runs[0].id); return; }
      renderSelectionState(state.runs.length ? 'Multiple active runs found. Choose the exact task above.' : 'No active run is available. Plotkeeper will not infer one.');
    } catch (error) {
      setConnection('error', 'API unavailable');
      $('#board-message').textContent = `Could not load runs (${error.message}).`;
      $('#board-message').classList.add('has-error');
    }
  }

  async function loadRun(id) {
    const runFromList = state.runs.find(run => run.id === id);
    if (!runFromList) { renderSelectionState('That run is not in the active inventory. Choose an active run.'); return; }
    state.selectionRequired = false; state.run = runFromList; setRunHeader(state.run); $('#check-in').disabled = false; setBoundUrl(state.run);
    try {
      const payload = await getJson(`/api/runs/${encodeURIComponent(id)}`);
      state.run = normalizeRun(payload?.run ?? payload);
      if (!state.run.id || state.run.id !== id) throw new Error('the API returned a different run');
      renderContract(payload?.contract ?? null);
      state.tasks = asArray(payload?.tasks ?? payload?.run?.tasks).map(normalizeTask);
      state.events = asArray(payload?.events ?? payload?.run?.events);
      state.reports = asArray(payload?.reports ?? payload?.run?.reports);
      state.sessions = asArray(payload?.sessions ?? payload?.run?.sessions);
      setRunHeader(state.run); renderBoard(state.tasks); selectTask(state.run.currentTaskId || state.tasks[0]?.id, false);
      $('#board-updated').textContent = state.run.updatedAt ? `Updated ${formatDate(state.run.updatedAt)}` : 'Updated time unknown';
    } catch (error) {
      renderSelectionState(`Run ${escape(id)} is unavailable (${error.message}). Plotkeeper did not fall back to another run.`);
    }
  }

  function groupTasks(tasks) {
    const groups = new Map();
    tasks.forEach(task => { if (!groups.has(task.workstream)) groups.set(task.workstream, []); groups.get(task.workstream).push(task); });
    return [...groups.entries()].map(([name, group]) => ({ name, tasks: group.filter(task => !task.parentId || !group.some(candidate => candidate.id === task.parentId)) }));
  }
  function childrenOf(task) { return state.tasks.filter(child => child.parentId === task.id); }
  function renderBoard(tasks) {
    const host = $('#workstreams'); host.replaceChildren(); const groups = groupTasks(tasks.filter(task => !state.filter || `${task.title} ${task.id} ${task.owner}`.toLowerCase().includes(state.filter)));
    $('#board-count').textContent = `${tasks.length} task${tasks.length === 1 ? '' : 's'} · ${groups.length} workstream${groups.length === 1 ? '' : 's'}`;
    $('#board-shell')?.classList.toggle('has-data', Boolean(tasks.length));
    if (!groups.length) { $('#board-message').hidden = false; if (!state.selectionRequired) $('#board-message').textContent = tasks.length ? 'No tasks match this filter.' : 'No tasks are attached to this run.'; return; } $('#board-message').hidden = true;
    groups.forEach((group, groupIndex) => {
      const section = document.createElement('section'); section.className = 'workstream is-open';
      const done = group.tasks.filter(task => /completed|done|closed/i.test(task.status)).length;
      section.innerHTML = `<button class="workstream-head" type="button" aria-expanded="true"><span class="chevron" aria-hidden="true">›</span><span><strong>${escape(group.name)}</strong><small>${group.tasks.length} top-level task${group.tasks.length === 1 ? '' : 's'}</small></span><span class="muted">${done}/${group.tasks.length}</span><span class="muted">${groupIndex + 1}</span></button><div class="workstream-body"></div>`;
      const body = $('.workstream-body', section); $('.workstream-head', section).addEventListener('click', () => { const open = section.classList.toggle('is-open'); $('.workstream-head', section).setAttribute('aria-expanded', String(open)); });
      group.tasks.forEach(task => body.appendChild(renderTask(task))); host.appendChild(section);
    });
  }
  function renderTask(task) {
    const row = document.createElement('article'); row.className = 'task-row'; row.dataset.taskId = task.id;
    const children = childrenOf(task); const current = task.id === state.run?.currentTaskId;
    row.innerHTML = `<button class="task-button" type="button" aria-expanded="${current}" aria-controls="subtasks-${escape(task.id)}"><span class="task-id">${escape(task.id)}</span><span class="task-title">${escape(task.title)}</span><span class="task-owner">${escape(task.owner)}</span><span class="task-status ${statusClass(task.status)}">${escape(statusLabel(task.status))}</span><span class="mini-progress" aria-label="${escape(formatProgress(task.progress))} complete"><span style="width:${task.progress === null ? 0 : Math.max(0, Math.min(100, task.progress))}%"></span></span><span class="chevron" aria-hidden="true">›</span></button><div class="subtasks" id="subtasks-${escape(task.id)}"></div>`;
    const button = $('.task-button', row); button.addEventListener('click', () => { const open = row.classList.toggle('is-open'); button.setAttribute('aria-expanded', String(open)); selectTask(task.id); });
    const subHost = $('.subtasks', row); children.forEach(child => { const sub = document.createElement('button'); sub.type = 'button'; sub.className = 'subtask'; sub.dataset.taskId = child.id; sub.innerHTML = `<span class="subtask-title">${escape(child.id)} · ${escape(child.title)}</span><small>${escape(child.owner)}</small><small class="${statusClass(child.status)}">${escape(statusLabel(child.status))}</small>`; sub.addEventListener('click', () => selectTask(child.id)); subHost.appendChild(sub); });
    if (current) { row.classList.add('is-open'); button.setAttribute('aria-expanded', 'true'); }
    return row;
  }

  function selectTask(id, scroll = true) {
    const task = state.tasks.find(candidate => candidate.id === id); if (!task) { clearDetail(); return; } state.selected = task.id;
    $$('.task-row').forEach(row => { const selected = row.dataset.taskId === task.id || childrenOf(state.tasks.find(item => item.id === row.dataset.taskId) || {}).some(child => child.id === task.id); row.classList.toggle('is-open', selected); });
    $$('.subtask').forEach(sub => sub.classList.toggle('is-selected', sub.dataset.taskId === task.id));
    $('#detail-path').textContent = `${task.workstream} · ${task.id}`; $('#detail-heading').textContent = task.title;
    const detailState = $('#detail-status'); detailState.className = `run-state ${statusClass(task.status)}`; detailState.textContent = statusLabel(task.status).toUpperCase();
    $('#working-title').textContent = task.title; $('#working-meta').textContent = `${statusLabel(task.status)} · ${task.owner} · ${formatProgress(task.progress)}`;
    $('#detail-change').textContent = task.purpose; $('#detail-return').textContent = task.summary;
    $('#detail-preserve').innerHTML = (task.preserve.length ? task.preserve : ['Evidence-backed status only.', 'A worker claim does not close the parent run.', 'Unrelated work remains outside this task.']).map(item => `<li>${escape(item)}</li>`).join('');
    renderTimeline(task); renderEvidence(task); renderReports(task); renderAgents(task); if (scroll) document.querySelector('.inspector')?.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
  }
  function clearDetail() { $('#detail-path').textContent = 'Run detail'; $('#detail-heading').textContent = 'Select a task'; $('#detail-status').textContent = 'UNKNOWN'; $('#detail-status').className = 'run-state state-unknown'; $('#working-title').textContent = 'No active task reported'; }
  function relatedEvents(task) { return state.events.filter(event => !event.task_id || event.task_id === task.id); }
  function renderTimeline(task) { const events = relatedEvents(task); $('#detail-timeline').innerHTML = events.length ? events.map(event => `<li class="timeline-item"><time>${escape(formatDate(event.timestamp ?? event.created_at))}</time><span class="timeline-dot" aria-hidden="true"></span><span>${escape(event.text ?? event.kind ?? 'State changed')}</span><span class="timeline-agent">${escape(event.agent_path ?? event.session_id ?? 'system')}</span></li>`).join('') : '<li class="empty-inline">No timeline events attached to this task.</li>'; }
  function renderEvidence(task) { const evidence = task.evidence.length ? task.evidence : relatedEvents(task).filter(event => event.evidence || event.receipt).map(event => event.evidence ?? event.receipt); $('#detail-evidence').innerHTML = evidence.length ? evidence.map(item => `<div class="detail-card"><strong>${escape(item.name ?? item.kind ?? 'Evidence')}</strong><p>${escape(item.result ?? item.status ?? item.value ?? item.path ?? item)}</p><small>${escape(item.authority ?? item.source ?? 'Authority not recorded')}</small></div>`).join('') : '<p class="empty-inline">No evidence attached. Plotkeeper will not infer success.</p>'; }
  function renderReports(task) { const reports = task.reports.length ? task.reports : state.reports; $('#detail-reports').innerHTML = reports.length ? reports.map(item => `<div class="detail-card"><strong>${escape(item.title ?? item.name ?? item.kind ?? 'Report')}</strong><p>${escape(item.summary ?? item.text ?? item.status ?? item)}</p><small>${escape(item.created_at ?? item.timestamp ?? 'Timestamp unknown')}</small></div>`).join('') : '<p class="empty-inline">No reports attached.</p>'; }
  function renderAgents(task) { const agents = state.sessions.filter(session => !session.task_id || session.task_id === task.id); $('#detail-agents').innerHTML = agents.length ? agents.map(agent => `<div class="agent-card"><span class="agent-avatar" aria-hidden="true">${escape(text(agent.agent_path ?? agent.session_id, '?').slice(0, 1).toUpperCase())}</span><span><strong>${escape(agent.agent_path ?? 'Agent identity unknown')}</strong><small>${escape(statusLabel(agent.status))} · session ${escape(agent.session_id ?? 'unknown')}</small></span></div>`).join('') : '<p class="empty-inline">No agent identities attached.</p>'; }

  $$('.tab').forEach(tab => tab.addEventListener('click', () => { $$('.tab').forEach(item => { const active = item === tab; item.classList.toggle('is-active', active); item.setAttribute('aria-selected', String(active)); }); $$('.inspector-panel').forEach(panel => panel.classList.toggle('is-visible', panel.dataset.panel === tab.dataset.tab)); }));
  $('#collapse-all').addEventListener('click', () => { $$('.workstream').forEach(section => { section.classList.remove('is-open'); $('.workstream-head', section)?.setAttribute('aria-expanded', 'false'); }); $$('.task-row').forEach(row => { row.classList.remove('is-open'); $('.task-button', row)?.setAttribute('aria-expanded', 'false'); }); });
  $('#task-filter').addEventListener('input', event => { state.filter = event.target.value.trim().toLowerCase(); renderBoard(state.tasks); if (state.selected) selectTask(state.selected, false); });
  $('#run-selector').addEventListener('change', event => { if (event.target.value) loadRun(event.target.value); });
  $('#check-in').addEventListener('click', async event => { const button = event.currentTarget; if (!state.run?.id) return; button.disabled = true; button.textContent = 'Sending…'; try { await getJson(`/api/runs/${encodeURIComponent(state.run.id)}/check-in`, { method: 'POST' }); button.classList.add('is-requested'); button.textContent = 'Check-in requested'; } catch (error) { button.disabled = false; button.textContent = 'Request failed'; button.title = error.message; } });
  loadRuns();
})();
