/* CCE-C1 Czech Exam Practice — Shared Logic */

(function () {
  'use strict';

  /* ── Tabs ── */
  function initTabs() {
    document.querySelectorAll('.tab-btn').forEach(btn => {
      btn.addEventListener('click', () => {
        const target = btn.dataset.tab;
        document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
        document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
        btn.classList.add('active');
        document.getElementById(target).classList.add('active');
      });
    });
  }

  /* ── Timer ── */
  const timers = {};

  function initTimer(sectionId, minutes) {
    const el = document.querySelector(`#${sectionId} .timer-display`);
    const pauseBtn = document.querySelector(`#${sectionId} .timer-pause`);
    if (!el) return;
    const totalSec = minutes * 60;
    timers[sectionId] = { remaining: totalSec, total: totalSec, running: false, interval: null, el };

    function render() {
      const t = timers[sectionId];
      const m = Math.floor(t.remaining / 60);
      const s = t.remaining % 60;
      el.textContent = `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
      el.classList.toggle('warning', t.remaining <= t.total * 0.25 && t.remaining > t.total * 0.1);
      el.classList.toggle('critical', t.remaining <= t.total * 0.1);
    }

    function tick() {
      const t = timers[sectionId];
      if (t.remaining <= 0) { clearInterval(t.interval); t.running = false; return; }
      t.remaining--;
      render();
    }

    render();

    if (pauseBtn) {
      pauseBtn.addEventListener('click', () => {
        const t = timers[sectionId];
        if (t.running) {
          clearInterval(t.interval);
          t.running = false;
          pauseBtn.textContent = '▶ Spustit';
        } else {
          t.interval = setInterval(tick, 1000);
          t.running = true;
          pauseBtn.textContent = '⏸ Pauza';
        }
      });
    }
  }

  function startTimer(sectionId) {
    const t = timers[sectionId];
    if (!t || t.running) return;
    t.interval = setInterval(() => {
      if (t.remaining <= 0) { clearInterval(t.interval); t.running = false; return; }
      t.remaining--;
      const m = Math.floor(t.remaining / 60);
      const s = t.remaining % 60;
      t.el.textContent = `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
      t.el.classList.toggle('warning', t.remaining <= t.total * 0.25 && t.remaining > t.total * 0.1);
      t.el.classList.toggle('critical', t.remaining <= t.total * 0.1);
    }, 1000);
    t.running = true;
  }

  /* ── ANO/NE toggles ── */
  function initToggles() {
    document.querySelectorAll('.toggle-btn').forEach(btn => {
      btn.addEventListener('click', () => {
        const group = btn.closest('.toggle-group');
        if (group.closest('.section-locked')) return;
        group.querySelectorAll('.toggle-btn').forEach(b => b.classList.remove('selected'));
        btn.classList.add('selected');
        saveProgress();
      });
    });
  }

  /* ── Topic selectors ── */
  function initTopicSelectors() {
    document.querySelectorAll('.topic-btn').forEach(btn => {
      btn.addEventListener('click', () => {
        const group = btn.closest('.topic-selector');
        group.querySelectorAll('.topic-btn').forEach(b => b.classList.remove('selected'));
        btn.classList.add('selected');
      });
    });
  }

  /* ── Word counter ── */
  function initWordCounters() {
    document.querySelectorAll('.writing-area').forEach(area => {
      const counter = area.parentElement.querySelector('.word-counter .count');
      if (!counter) return;
      function update() {
        const words = area.value.trim().split(/\s+/).filter(w => w.length > 0).length;
        counter.textContent = words;
        counter.className = 'count ' + (words >= 350 ? 'ok' : 'under');
      }
      area.addEventListener('input', update);
      update();
    });
  }

  /* ── Collect answers ── */
  function collectAnswers(sectionId) {
    const section = document.getElementById(sectionId);
    if (!section) return {};
    const answers = {};

    // Dropdowns
    section.querySelectorAll('.q-select[data-q]').forEach(sel => {
      answers[sel.dataset.q] = sel.value || '';
    });
    // Text inputs
    section.querySelectorAll('.q-input[data-q]').forEach(inp => {
      answers[inp.dataset.q] = inp.value.trim();
    });
    // Radio buttons
    section.querySelectorAll('input[type="radio"]:checked').forEach(radio => {
      answers[radio.name] = radio.value;
    });
    // ANO/NE toggles
    section.querySelectorAll('.toggle-group[data-q]').forEach(group => {
      const sel = group.querySelector('.toggle-btn.selected');
      answers[group.dataset.q] = sel ? sel.dataset.value : '';
    });

    return answers;
  }

  /* ── Normalize for comparison ── */
  function normalize(str) {
    return str.toLowerCase().trim()
      .replace(/\s+/g, ' ')
      .replace(/[.,;:!?]/g, '');
  }

  /* ── Score a section ── */
  function scoreSection(sectionId, answerKey, pointsMap) {
    const userAnswers = collectAnswers(sectionId);
    const results = { total: 0, max: 0, perQuestion: {} };

    for (const [qId, correct] of Object.entries(answerKey)) {
      const pts = pointsMap[qId] || 1;
      results.max += pts;
      const userVal = userAnswers[qId] || '';

      let isCorrect = false;
      if (Array.isArray(correct)) {
        // Multiple accepted answers (for open fill-in)
        isCorrect = correct.some(c => normalize(c) === normalize(userVal));
      } else {
        isCorrect = normalize(String(correct)) === normalize(String(userVal));
      }

      if (isCorrect) results.total += pts;
      results.perQuestion[qId] = { user: userVal, correct, isCorrect, pts };
    }

    return results;
  }

  /* ── Lock section ── */
  function lockSection(sectionId) {
    const section = document.getElementById(sectionId);
    if (!section) return;
    section.classList.add('section-locked');
    const lockBtn = section.querySelector('.lock-btn');
    if (lockBtn) lockBtn.disabled = true;
    const msg = section.querySelector('.section-locked-msg');
    if (msg) msg.style.display = 'block';
    // Stop timer
    const t = timers[sectionId];
    if (t && t.running) {
      clearInterval(t.interval);
      t.running = false;
    }
  }

  /* ── Show review (correct/wrong highlights) ── */
  function showReview(sectionId, scoreResult) {
    const section = document.getElementById(sectionId);
    if (!section) return;

    for (const [qId, info] of Object.entries(scoreResult.perQuestion)) {
      // Find the question element
      const el = section.querySelector(`[data-q="${qId}"]`);
      if (!el) continue;
      const item = el.closest('.question-item') || el.closest('.bq-item');
      if (!item) continue;

      if (info.isCorrect) {
        item.classList.add('review-correct');
      } else {
        item.classList.add('review-wrong');
        // Add correct answer hint
        let hint = item.querySelector('.correct-answer-hint');
        if (!hint) {
          hint = document.createElement('div');
          hint.className = 'correct-answer-hint';
          item.appendChild(hint);
        }
        const correctStr = Array.isArray(info.correct) ? info.correct.join(' / ') : info.correct;
        hint.textContent = `Správně: ${correctStr}`;
      }
    }
  }

  /* ── Results dashboard ── */
  function showResults(sections) {
    const overlay = document.getElementById('results-overlay');
    if (!overlay) return;

    let allPass = true;
    let html = '<h2>Výsledky testu</h2>';

    // Check auto-gradable sections
    const autoSections = sections.filter(s => s.autoGradable);
    const passAll = autoSections.every(s => s.score.total / s.score.max >= 0.6);

    // Overall
    if (passAll) {
      html += '<div class="overall-result pass">USPĚL/A (ve všech hodnocených subtestech)</div>';
    } else {
      html += '<div class="overall-result fail">NEUSPĚL/A</div>';
    }

    // Per section
    for (const s of sections) {
      const pct = s.autoGradable ? Math.round(s.score.total / s.score.max * 100) : null;
      const pass = pct !== null ? pct >= 60 : null;
      const badgeClass = pass === null ? 'badge-na' : (pass ? 'badge-pass' : 'badge-fail');
      const badgeText = pass === null ? 'N/A' : (pass ? 'PASS' : 'FAIL');

      html += `<div class="subtest-result">
        <span class="name">${s.name}</span>
        <span class="score">
          <span class="points">${s.autoGradable ? s.score.total : '—'} / ${s.score.max}</span>
          <span class="pct">${pct !== null ? pct + '%' : 'nehodnoceno'}</span>
          <span class="badge ${badgeClass}">${badgeText}</span>
        </span>
      </div>`;

      if (!s.autoGradable && pass === null) continue;
      if (pass === false) allPass = false;
    }

    // Breakdown
    html += '<div class="breakdown-section">';
    for (const s of sections) {
      if (!s.autoGradable || !s.score.perQuestion) continue;
      html += `<h3 onclick="this.nextElementSibling.classList.toggle('open')">▸ ${s.name} — podrobnosti</h3>`;
      html += '<div class="breakdown-list">';
      for (const [qId, info] of Object.entries(s.score.perQuestion)) {
        const cls = info.isCorrect ? 'correct' : 'wrong';
        const correctStr = Array.isArray(info.correct) ? info.correct.join(' / ') : info.correct;
        html += `<div class="bq-item ${cls}">
          <span class="bq-num">${qId}</span>
          <span class="bq-user">${info.user || '—'}</span>
          <span class="bq-correct">správně: ${correctStr}</span>
        </div>`;
      }
      html += '</div>';
    }
    html += '</div>';

    html += '<div style="text-align:center;margin-top:1.5rem"><button class="btn btn-primary" onclick="document.getElementById(\'results-overlay\').classList.remove(\'visible\')">Zavřít</button></div>';

    overlay.querySelector('.results-panel').innerHTML = html;
    overlay.classList.add('visible');
  }

  /* ── Local storage ── */
  function getStorageKey() {
    return 'cce-c1-' + (document.body.dataset.testId || 'unknown');
  }

  function saveProgress() {
    const key = getStorageKey();
    const data = {};
    // Save all inputs
    document.querySelectorAll('.q-select[data-q]').forEach(el => { data['s_' + el.dataset.q] = el.value; });
    document.querySelectorAll('.q-input[data-q]').forEach(el => { data['i_' + el.dataset.q] = el.value; });
    document.querySelectorAll('input[type="radio"]:checked').forEach(el => { data['r_' + el.name] = el.value; });
    document.querySelectorAll('.toggle-group[data-q]').forEach(g => {
      const sel = g.querySelector('.toggle-btn.selected');
      data['t_' + g.dataset.q] = sel ? sel.dataset.value : '';
    });
    document.querySelectorAll('.writing-area').forEach(el => { data['w_' + el.id] = el.value; });
    try { localStorage.setItem(key, JSON.stringify(data)); } catch (e) {}
  }

  function loadProgress() {
    const key = getStorageKey();
    let data;
    try { data = JSON.parse(localStorage.getItem(key)); } catch (e) { return; }
    if (!data) return;

    for (const [k, v] of Object.entries(data)) {
      if (k.startsWith('s_')) {
        const el = document.querySelector(`.q-select[data-q="${k.slice(2)}"]`);
        if (el) el.value = v;
      } else if (k.startsWith('i_')) {
        const el = document.querySelector(`.q-input[data-q="${k.slice(2)}"]`);
        if (el) el.value = v;
      } else if (k.startsWith('r_')) {
        const name = k.slice(2);
        const radio = document.querySelector(`input[type="radio"][name="${name}"][value="${v}"]`);
        if (radio) radio.checked = true;
      } else if (k.startsWith('t_')) {
        const group = document.querySelector(`.toggle-group[data-q="${k.slice(2)}"]`);
        if (group && v) {
          const btn = group.querySelector(`.toggle-btn[data-value="${v}"]`);
          if (btn) { group.querySelectorAll('.toggle-btn').forEach(b => b.classList.remove('selected')); btn.classList.add('selected'); }
        }
      } else if (k.startsWith('w_')) {
        const el = document.getElementById(k.slice(2));
        if (el) el.value = v;
      }
    }
  }

  function clearProgress() {
    try { localStorage.removeItem(getStorageKey()); } catch (e) {}
  }

  /* ── Auto-save on change ── */
  function initAutoSave() {
    document.addEventListener('change', saveProgress);
    document.addEventListener('input', (e) => {
      if (e.target.matches('.q-input, .writing-area')) saveProgress();
    });
  }

  /* ── Expose API ── */
  window.CCE = {
    initTabs,
    initTimer,
    startTimer,
    initToggles,
    initTopicSelectors,
    initWordCounters,
    collectAnswers,
    scoreSection,
    lockSection,
    showReview,
    showResults,
    saveProgress,
    loadProgress,
    clearProgress,
    initAutoSave,
    timers
  };
})();
