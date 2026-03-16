const SCAM_KEYWORDS = [
  'free money', 'click this link', 'forward to', 'share with',
  'limited time', 'expires tonight', 'you have won', 'claim now',
  'government scheme', 'pm yojana', 'free recharge', 'otp',
  'aadhaar', 'pan card', 'urgent', 'act now', 'lottery', 'prize',
  'मुफ्त', 'फ्री', 'आगे भेजें', 'तुरंत', 'अभी करें',
  'सरकार दे रही', 'आधार', 'पैसे मिलेंगे', 'फॉरवर्ड करें'
];

const HIGH_RISK_PATTERNS = [
  /forward.{0,20}(people|friends|contacts|लोगों)/i,
  /\d+\s*(hours?|minutes?|घंटे|मिनट).{0,20}(expire|बंद|खत्म)/i,
  /(free|मुफ्त|फ्री).{0,30}(₹|\$|money|पैसे|रुपए)/i,
  /(government|सरकार).{0,30}(giving|दे रही|scheme|योजना)/i,
  /share.{0,20}\d+.{0,20}(contacts|people|friends)/i,
];

let processedMessages = new Set();

function analyzeText(text) {
  const lower = text.toLowerCase();
  let riskScore = 0;
  let triggers = [];

  SCAM_KEYWORDS.forEach(kw => {
    if (lower.includes(kw.toLowerCase())) {
      riskScore += 10;
      triggers.push(kw);
    }
  });

  HIGH_RISK_PATTERNS.forEach(pattern => {
    if (pattern.test(text)) riskScore += 25;
  });

  if (/[!]{2,}/.test(text)) riskScore += 10;
  if (/[A-Z]{5,}/.test(text)) riskScore += 10;
  if (text.includes('http') || text.includes('www')) riskScore += 15;

  return {
    score: Math.min(riskScore, 100),
    triggers: [...new Set(triggers)].slice(0, 3)
  };
}

function showWarning(messageEl, risk) {
  if (messageEl.querySelector('.tg-warning')) return;

  const isHighRisk = risk.score >= 50;
  const warning = document.createElement('div');
  warning.className = 'tg-warning';
  warning.innerHTML = `
    <div class="tg-inner ${isHighRisk ? 'tg-high' : 'tg-medium'}">
      <div class="tg-header">
        <span class="tg-icon">${isHighRisk ? '🚨' : '⚠️'}</span>
        <span class="tg-title">TruthGuard AI — ${isHighRisk ? 'High risk' : 'Suspicious'}</span>
        <button class="tg-close" onclick="this.closest('.tg-warning').remove()">✕</button>
      </div>
      <div class="tg-body">
        <div class="tg-score-row">
          <span class="tg-score-label">Risk score</span>
          <div class="tg-bar-wrap"><div class="tg-bar" style="width:${risk.score}%"></div></div>
          <span class="tg-score-num">${risk.score}%</span>
        </div>
        ${risk.triggers.length ? `<div class="tg-triggers">${risk.triggers.map(t => `<span class="tg-tag">${t}</span>`).join('')}</div>` : ''}
        <div class="tg-actions">
          <span class="tg-tip">Verify before sharing</span>
          <a href="http://127.0.0.1:5500/app.html" target="_blank" class="tg-btn">Verify now →</a>
        </div>
      </div>
    </div>`;
  messageEl.appendChild(warning);
}

function scanMessages() {
  const messages = document.querySelectorAll(
    '[data-testid="msg-container"], .message-in, ._21Ahp'
  );
  messages.forEach(msg => {
    const msgId = msg.textContent.slice(0, 50);
    if (processedMessages.has(msgId)) return;
    processedMessages.add(msgId);
    const textEl = msg.querySelector('span.selectable-text, .copyable-text span');
    if (!textEl) return;
    const text = textEl.textContent || '';
    if (text.length < 20) return;
    const risk = analyzeText(text);
    if (risk.score >= 30) showWarning(msg, risk);
  });
}

function startObserver() {
  const chatArea = document.querySelector('#main, [data-testid="conversation-panel-wrapper"]');
  if (chatArea) {
    new MutationObserver(scanMessages).observe(chatArea, { childList: true, subtree: true });
    scanMessages();
    console.log('✅ TruthGuard AI is watching WhatsApp Web');
  } else {
    setTimeout(startObserver, 2000);
  }
}

startObserver();