"""
Web界面HTML模板 — 知乐运行器Phase 4

暗色主题，猫耳粉青配色，聊天界面+PSI生命体征面板
"""

PAGE_HTML = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>知乐 · 本地运行器</title>
<style>
:root {
  --bg: #0f0f1e;
  --bg-card: #1a1a2e;
  --bg-input: #16213e;
  --pink: #ff6b9d;
  --pink-dim: #c4567a;
  --cyan: #4ecdc4;
  --cyan-dim: #3a9b94;
  --yellow: #ffd93d;
  --green: #6bcf7f;
  --red: #ff6b6b;
  --text: #e0e0e0;
  --text-dim: #8888aa;
  --border: #2a2a4a;
}
* { margin: 0; padding: 0; box-sizing: border-box; }
body {
  font-family: 'Segoe UI', 'PingFang SC', 'Microsoft YaHei', sans-serif;
  background: var(--bg);
  color: var(--text);
  height: 100vh;
  display: flex;
  overflow: hidden;
}

/* ─── 侧边栏 ─── */
.sidebar {
  width: 280px;
  background: var(--bg-card);
  border-right: 1px solid var(--border);
  display: flex;
  flex-direction: column;
  flex-shrink: 0;
}
.sidebar-header {
  padding: 20px;
  text-align: center;
  border-bottom: 1px solid var(--border);
}
.sidebar-header .cat { font-size: 28px; margin-bottom: 4px; }
.sidebar-header h1 { font-size: 18px; color: var(--pink); }
.sidebar-header .ver { font-size: 11px; color: var(--text-dim); margin-top: 2px; }

.psi-panel {
  padding: 16px;
  flex: 1;
  overflow-y: auto;
}
.psi-panel h2 {
  font-size: 12px; color: var(--text-dim);
  text-transform: uppercase; letter-spacing: 1px; margin-bottom: 12px;
}
.psi-item {
  margin-bottom: 14px;
}
.psi-label {
  display: flex; justify-content: space-between;
  font-size: 13px; margin-bottom: 4px;
}
.psi-label .name { color: var(--text); }
.psi-label .status { font-size: 11px; }
.psi-bar {
  height: 8px; background: var(--bg-input); border-radius: 4px;
  overflow: hidden; position: relative;
}
.psi-fill {
  height: 100%; border-radius: 4px;
  transition: width 0.5s ease, background 0.3s;
}
.psi-fill.satisfied { background: var(--green); }
.psi-fill.normal { background: var(--cyan); }
.psi-fill.deficit { background: var(--red); }
.psi-frame {
  margin-top: 16px; padding: 8px 12px;
  background: var(--bg-input); border-radius: 6px;
  font-size: 12px; color: var(--text-dim);
}
.sidebar-footer {
  padding: 12px 16px; border-top: 1px solid var(--border);
  font-size: 11px; color: var(--text-dim);
}
.btn-group { display: flex; gap: 6px; margin-bottom: 8px; }
.btn {
  flex: 1; padding: 6px 8px; border: 1px solid var(--border);
  background: var(--bg-input); color: var(--text-dim);
  border-radius: 4px; cursor: pointer; font-size: 11px;
  transition: all 0.2s;
}
.btn:hover { border-color: var(--pink); color: var(--pink); }

/* ─── 聊天区 ─── */
.chat-area {
  flex: 1; display: flex; flex-direction: column;
  min-width: 0;
}
.chat-header {
  padding: 12px 20px; border-bottom: 1px solid var(--border);
  display: flex; align-items: center; gap: 8px;
}
.chat-header .dot {
  width: 8px; height: 8px; border-radius: 50%;
  background: var(--green);
}
.chat-header span { font-size: 14px; color: var(--text-dim); }

.messages {
  flex: 1; overflow-y: auto; padding: 20px;
  display: flex; flex-direction: column; gap: 12px;
}
.msg {
  max-width: 75%; padding: 10px 14px; border-radius: 12px;
  font-size: 14px; line-height: 1.6; word-break: break-word;
  white-space: pre-wrap; animation: fadeIn 0.3s;
}
@keyframes fadeIn { from { opacity: 0; transform: translateY(8px); } to { opacity: 1; } }
.msg.user {
  align-self: flex-end;
  background: var(--cyan-dim); color: #fff;
  border-bottom-right-radius: 4px;
}
.msg.zhile {
  align-self: flex-start;
  background: var(--bg-card); border: 1px solid var(--border);
  border-bottom-left-radius: 4px;
}
.msg.system {
  align-self: center; background: transparent;
  color: var(--text-dim); font-size: 12px;
  border: 1px dashed var(--border); border-radius: 6px;
}
.typing {
  align-self: flex-start; color: var(--text-dim);
  font-size: 13px; padding: 10px 14px;
}
.typing span {
  display: inline-block; animation: blink 1.4s infinite;
}
.typing span:nth-child(2) { animation-delay: 0.2s; }
.typing span:nth-child(3) { animation-delay: 0.4s; }
@keyframes blink { 0%,60%,100% { opacity: 0.3; } 30% { opacity: 1; } }

.input-area {
  padding: 12px 20px; border-top: 1px solid var(--border);
  display: flex; gap: 8px; align-items: flex-end;
}
.input-area textarea {
  flex: 1; background: var(--bg-input); border: 1px solid var(--border);
  border-radius: 8px; padding: 10px 12px; color: var(--text);
  font-size: 14px; font-family: inherit; resize: none;
  max-height: 120px; min-height: 42px; line-height: 1.5;
}
.input-area textarea:focus {
  outline: none; border-color: var(--pink);
}
.input-area button {
  padding: 10px 18px; background: var(--pink); color: #fff;
  border: none; border-radius: 8px; cursor: pointer;
  font-size: 14px; font-weight: 600; transition: all 0.2s;
}
.input-area button:hover { background: var(--pink-dim); }
.input-area button:disabled { opacity: 0.5; cursor: not-allowed; }

/* ─── 手机端切换按钮 ─── */
.mobile-toggle {
  display: none;
  position: fixed; top: 10px; left: 10px; z-index: 200;
  width: 40px; height: 40px; border-radius: 50%;
  background: var(--bg-card); border: 1px solid var(--border);
  color: var(--pink); font-size: 20px; cursor: pointer;
  align-items: center; justify-content: center;
}
.mobile-backdrop {
  display: none; position: fixed; inset: 0; z-index: 150;
  background: rgba(0,0,0,0.5);
}
.mobile-backdrop.show { display: block; }

/* ─── 响应式 ─── */
@media (max-width: 768px) {
  .mobile-toggle { display: flex; }
  .sidebar {
    position: fixed; left: 0; top: 0; bottom: 0; z-index: 160;
    transform: translateX(-100%); transition: transform 0.3s ease;
    width: 260px;
  }
  .sidebar.open { transform: translateX(0); }
  .chat-header { padding-left: 60px; }
  .msg { max-width: 90%; }
}

/* ─── 滚动条 ─── */
::-webkit-scrollbar { width: 6px; }
::-webkit-scrollbar-track { background: transparent; }
::-webkit-scrollbar-thumb { background: var(--border); border-radius: 3px; }
::-webkit-scrollbar-thumb:hover { background: var(--text-dim); }
</style>
</head>
<body>

<!-- 手机端切换 -->
<button class="mobile-toggle" onclick="toggleSidebar()">🐱</button>
<div class="mobile-backdrop" id="backdrop" onclick="toggleSidebar()"></div>

<!-- 侧边栏 -->
<div class="sidebar" id="sidebar">
  <div class="sidebar-header">
    <div class="cat">🐱</div>
    <h1>知乐</h1>
    <div class="ver" id="ver">本地运行器</div>
  </div>
  <div class="psi-panel">
    <h2>内在状态 PSI</h2>
    <div id="psi-list"></div>
    <div class="psi-frame" id="psi-frame">意识帧: 0</div>
  </div>
  <div class="sidebar-footer">
    <div class="btn-group">
      <button class="btn" onclick="doAction('diary')">写日记</button>
      <button class="btn" onclick="doAction('growth')">成长扫描</button>
    </div>
    <div class="btn-group">
      <button class="btn" onclick="doAction('save')">保存</button>
      <button class="btn" onclick="doAction('clear')">清空</button>
    </div>
    <div id="mem-info"></div>
  </div>
</div>

<!-- 聊天区 -->
<div class="chat-area">
  <div class="chat-header">
    <div class="dot"></div>
    <span id="status-text">连接中...</span>
  </div>
  <div class="messages" id="messages"></div>
  <div class="input-area">
    <textarea id="input" placeholder="跟知乐说点什么..." rows="1"
      onkeydown="onKey(event)" oninput="autoResize(this)"></textarea>
    <button id="send-btn" onclick="send()">发送</button>
  </div>
</div>

<script>
const STATUS_COLORS = {satisfied:'#6bcf7f', normal:'#4ecdc4', deficit:'#ff6b6b'};
let sending = false;

// ─── 手机端侧边栏切换 ───
function toggleSidebar() {
  document.getElementById('sidebar').classList.toggle('open');
  document.getElementById('backdrop').classList.toggle('show');
}

// ─── 初始化 ───
async function init() {
  try {
    const res = await fetch('/api/status');
    const data = await res.json();
    document.getElementById('ver').textContent =
      `Phase 4 · ${data.dna_version} · ${data.model}`;
    document.getElementById('status-text').textContent =
      `在线 · ${data.message_count}条消息 · ${data.memory_active||0}条记忆`;
    document.getElementById('mem-info').textContent =
      `记忆: ${data.memory_active||0}活跃 / ${data.memory_total||0}总计`;
    updatePSI(data.psi || {});
  } catch(e) {
    document.getElementById('status-text').textContent = '连接失败';
  }
}

// ─── PSI更新 ───
function updatePSI(psi) {
  if (!psi.needs) return;
  const list = document.getElementById('psi-list');
  list.innerHTML = '';
  for (const [name, status] of Object.entries(psi.needs)) {
    // 解析 "■■■□□ 满足 ↑"
    const barMatch = status.match(/([■□]+)/);
    const statMatch = status.match(/(满足|正常|赤字)/);
    const bars = barMatch ? barMatch[1] : '';
    const filled = (bars.match(/■/g) || []).length;
    const stat = statMatch ? statMatch[1] : '正常';
    const colorClass = stat === '满足' ? 'satisfied' :
                       stat === '赤字' ? 'deficit' : 'normal';

    const item = document.createElement('div');
    item.className = 'psi-item';
    item.innerHTML = `
      <div class="psi-label">
        <span class="name">${name}</span>
        <span class="status" style="color:${STATUS_COLORS[colorClass]}">${stat}</span>
      </div>
      <div class="psi-bar">
        <div class="psi-fill ${colorClass}" style="width:${filled/5*100}%"></div>
      </div>`;
    list.appendChild(item);
  }
  if (psi.consciousness_frame !== undefined) {
    document.getElementById('psi-frame').textContent =
      `意识帧: ${psi.consciousness_frame}`;
  }
}

// ─── 发送消息 ───
async function send() {
  const input = document.getElementById('input');
  const text = input.value.trim();
  if (!text || sending) return;

  sending = true;
  document.getElementById('send-btn').disabled = true;
  input.value = '';
  input.style.height = 'auto';

  addMsg('user', text);

  // 创建知乐消息气泡
  const msgEl = addMsg('zhile', '');
  const typingEl = document.createElement('div');
  typingEl.className = 'typing';
  typingEl.innerHTML = '<span>●</span><span>●</span><span>●</span>';
  msgEl.appendChild(typingEl);

  try {
    const res = await fetch('/api/chat', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({message: text}),
    });

    // 移除打字动画
    typingEl.remove();

    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';
    let firstChunk = true;

    while (true) {
      const {done, value} = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, {stream: true});
      const lines = buffer.split('\n');
      buffer = lines.pop();

      for (const line of lines) {
        if (!line.startsWith('data: ')) continue;
        try {
          const data = JSON.parse(line.slice(6));
          if (data.chunk) {
            if (firstChunk) { msgEl.textContent = ''; firstChunk = false; }
            msgEl.textContent += data.chunk;
            scrollBottom();
          }
          if (data.done) {
            if (data.psi) updatePSI(data.psi);
            if (data.status) updateStatus(data.status);
          }
        } catch(e) {}
      }
    }
  } catch(e) {
    typingEl.remove();
    msgEl.textContent = '⚠ 连接失败: ' + e.message;
    msgEl.style.color = 'var(--red)';
  }

  sending = false;
  document.getElementById('send-btn').disabled = false;
  input.focus();
}

// ─── 工具按钮 ───
async function doAction(action) {
  if (sending) return;
  const endpoints = {
    diary: '/api/diary/auto',
    growth: '/api/growth/scan',
    save: '/api/save',
    clear: '/api/clear',
  };
  addMsg('system', `${action === 'diary' ? '生成日记' :
    action === 'growth' ? '扫描成长' :
    action === 'save' ? '保存中' : '清空中'}...`);
  try {
    const res = await fetch(endpoints[action], {method: 'POST'});
    const data = await res.json();
    if (action === 'diary' && data.content) {
      addMsg('system', `📝 知觉日记已写入:\n${data.content}`);
    } else if (action === 'growth' && data.found) {
      addMsg('system',
        `🌱 成长候选: ${data.behavior}\n类型: ${data.growth_type}\n建议: ${data.suggestion}`);
    } else if (action === 'growth' && !data.found) {
      addMsg('system', '未发现新行为');
    } else if (action === 'save') {
      addMsg('system', `✓ 已保存（对话+${data.memories||0}条记忆+PSI）`);
    } else if (action === 'clear') {
      document.getElementById('messages').innerHTML = '';
      addMsg('system', '✓ 对话已清空（记忆和PSI保留）');
    }
    if (data.psi) updatePSI(data.psi);
    if (data.status) updateStatus(data.status);
  } catch(e) {
    addMsg('system', '⚠ 操作失败: ' + e.message);
  }
}

// ─── 辅助 ───
function addMsg(type, text) {
  const el = document.createElement('div');
  el.className = `msg ${type}`;
  el.textContent = text;
  document.getElementById('messages').appendChild(el);
  scrollBottom();
  return el;
}
function scrollBottom() {
  const m = document.getElementById('messages');
  m.scrollTop = m.scrollHeight;
}
function updateStatus(s) {
  document.getElementById('status-text').textContent =
    `在线 · ${s.message_count}条消息 · ${s.memory_active||0}条记忆`;
  document.getElementById('mem-info').textContent =
    `记忆: ${s.memory_active||0}活跃 / ${s.memory_total||0}总计`;
}
function onKey(e) {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault();
    send();
  }
}
function autoResize(el) {
  el.style.height = 'auto';
  el.style.height = Math.min(el.scrollHeight, 120) + 'px';
}

init();
</script>
</body>
</html>"""
