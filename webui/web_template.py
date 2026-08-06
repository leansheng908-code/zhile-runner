"""
Web界面HTML模板 — 知乐运行器 P0.38 Phase 1.5 UI猫娘化

暖色猫娘美学主题，猫耳装饰+爪印动效+完整命令面板
聊天界面 + PSI生命体征面板 + 40+命令全映射
"""

PAGE_HTML = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>知乐 · 本地运行器</title>
<style>
:root {
  /* ─── 暖粉猫娘色彩系统（浅色版） ─── */
  --bg: #fdf6f7;            /* 暖奶粉底色 */
  --bg-card: #fff0f3;       /* 浅粉卡片 */
  --bg-input: #fce7ec;      /* 柔粉输入框 */
  --pink: #ff6b9d;           /* 亮粉 */
  --pink-dim: #e85d88;       /* 深粉 */
  --pink-glow: rgba(255,107,157,0.12);
  --cream: #ffffff;          /* 纯白 */
  --cyan: #4db6ac;           /* 青绿 */
  --cyan-dim: #3a9b91;       /* 深青绿 */
  --yellow: #ffb74d;         /* 暖黄 */
  --green: #66bb6a;           /* 清新绿 */
  --red: #ef5350;            /* 暖红 */
  --text: #4a3a44;           /* 暖深灰（可读） */
  --text-dim: #8a7a84;       /* 中暖灰 */
  --border: #f0d5dd;         /* 浅粉边框 */
  --radius: 16px;
  --shadow: 0 4px 16px rgba(255,107,157,0.08);
  --shadow-hover: 0 6px 24px rgba(255,107,157,0.15);
}
* { margin: 0; padding: 0; box-sizing: border-box; }
body {
  font-family: 'Segoe UI', 'PingFang SC', 'Microsoft YaHei', sans-serif;
  background-color: var(--bg);
  background: var(--bg);
  color: var(--text);
  height: 100vh;
  display: flex;
  overflow: hidden;
  user-select: text;
  -webkit-user-select: text;
}

/* ─── 猫尾巴装饰（侧边栏顶部） ─── */
.cat-tail {
  position: absolute;
  top: 0;
  right: -6px;
  width: 60px;
  height: 50px;
  overflow: visible;
  pointer-events: none;
  z-index: 10;
}
.cat-tail::before {
  content: '';
  position: absolute;
  top: 8px;
  right: 10px;
  width: 36px;
  height: 36px;
  border: 3px solid transparent;
  border-right-color: var(--pink);
  border-radius: 50%;
  animation: tailWag 4s ease-in-out infinite;
  transform-origin: bottom left;
}
@keyframes tailWag {
  0%, 100% { transform: rotate(-20deg); }
  50% { transform: rotate(15deg); }
}

/* ─── 侧边栏 ─── */
.sidebar {
  width: 280px;
  background: var(--bg-card);
  border-right: 1px solid var(--border);
  display: flex;
  flex-direction: column;
  flex-shrink: 0;
  position: relative;
}

/* ─── 头像区域（猫耳装饰） ─── */
.sidebar-header {
  padding: 24px 20px 16px;
  text-align: center;
  border-bottom: 1px solid var(--border);
  position: relative;
}
.avatar-wrapper {
  display: inline-block;
  position: relative;
  margin-bottom: 4px;
}
.avatar-wrapper::before,
.avatar-wrapper::after {
  content: '';
  position: absolute;
  top: -14px;
  width: 0;
  height: 0;
  border-left: 12px solid transparent;
  border-right: 12px solid transparent;
  border-bottom: 20px solid var(--pink);
  filter: drop-shadow(0 1px 2px rgba(255,143,171,0.3));
}
.avatar-wrapper::before {
  left: -18px;
  transform: rotate(-18deg);
  animation: earWiggleL 3s ease-in-out infinite;
}
.avatar-wrapper::after {
  right: -18px;
  transform: rotate(18deg);
  animation: earWiggleR 3s ease-in-out infinite;
}
@keyframes earWiggleL {
  0%, 100% { transform: rotate(-18deg); }
  50% { transform: rotate(-8deg); }
}
@keyframes earWiggleR {
  0%, 100% { transform: rotate(18deg); }
  50% { transform: rotate(8deg); }
}
.avatar-emoji {
  font-size: 48px;
  display: inline-block;
  transition: transform 0.3s;
  animation: avatarBounce 2s ease-in-out infinite;
}
@keyframes avatarBounce {
  0%, 100% { transform: translateY(0); }
  50% { transform: translateY(-4px); }
}
.avatar-label {
  font-size: 11px;
  color: var(--cyan);
  margin-bottom: 2px;
}
.sidebar-header h1 {
  font-size: 18px;
  color: var(--pink);
  text-shadow: 0 0 12px rgba(255,143,171,0.3);
}
.sidebar-header .ver {
  font-size: 11px;
  color: var(--text-dim);
  margin-top: 2px;
}

/* ─── PSI 面板 ─── */
.psi-panel {
  padding: 16px;
  flex: 1;
  overflow-y: auto;
}
.psi-panel h2 {
  font-size: 13px;
  color: var(--pink);
  text-transform: none;
  letter-spacing: 0.5px;
  margin-bottom: 12px;
}
.psi-item {
  margin-bottom: 14px;
}
.psi-label {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-size: 13px;
  margin-bottom: 4px;
}
.psi-label .name { color: var(--text); }
.psi-label .name::before {
  content: '🐾 ';
  font-size: 10px;
}
.psi-label .status { font-size: 11px; }

/* PSI 进度条 — 猫爪渐变填充 */
.psi-bar {
  height: 10px;
  background: var(--bg-input);
  border-radius: 8px;
  overflow: hidden;
  position: relative;
  border: 1px solid var(--border);
}
.psi-fill {
  height: 100%;
  border-radius: 8px;
  transition: width 0.5s ease;
  position: relative;
  background-size: 24px 24px;
  background-image: radial-gradient(circle, rgba(255,255,255,0.15) 2px, transparent 2px);
  background-repeat: repeat;
  animation: psiFlow 2s linear infinite;
}
@keyframes psiFlow {
  0% { background-position: 0 0; }
  100% { background-position: 24px 0; }
}
.psi-fill.satisfied {
  background-color: var(--green);
  background-image: radial-gradient(circle, rgba(255,255,255,0.2) 2px, transparent 2px), linear-gradient(90deg, var(--green), var(--cyan));
}
.psi-fill.normal {
  background-color: var(--cyan);
  background-image: radial-gradient(circle, rgba(255,255,255,0.15) 2px, transparent 2px), linear-gradient(90deg, var(--cyan-dim), var(--cyan));
}
.psi-fill.deficit {
  background-color: var(--red);
  background-image: radial-gradient(circle, rgba(255,255,255,0.15) 2px, transparent 2px), linear-gradient(90deg, var(--red), var(--pink-dim));
}

/* 意识帧 ✨ 装饰 */
.psi-frame {
  margin-top: 16px;
  padding: 10px 14px;
  background: var(--bg-input);
  border-radius: var(--radius);
  border: 1px solid var(--border);
  font-size: 12px;
  color: var(--text-dim);
  display: flex;
  align-items: center;
  gap: 6px;
}
.psi-frame::before {
  content: '✨';
  font-size: 14px;
}

/* ─── 侧边栏底部 ─── */
.sidebar-footer {
  padding: 12px 16px;
  border-top: 1px solid var(--border);
  font-size: 11px;
  color: var(--text-dim);
}
.btn-group { display: flex; gap: 6px; margin-bottom: 8px; }
.btn {
  flex: 1;
  padding: 7px 8px;
  border: 1px solid var(--border);
  background: var(--bg-input);
  color: var(--text-dim);
  border-radius: 10px;
  cursor: pointer;
  font-size: 11px;
  transition: all 0.2s;
}
.btn:hover {
  border-color: var(--pink);
  color: var(--pink);
  box-shadow: var(--shadow);
}

/* ─── 聊天区 ─── */
.chat-area {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-width: 0;
}
.chat-header {
  padding: 12px 20px;
  border-bottom: 1px solid var(--border);
  display: flex;
  align-items: center;
  gap: 8px;
}
.chat-header .dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--green);
  box-shadow: 0 0 8px var(--green);
}
.chat-header span { font-size: 14px; color: var(--text-dim); }

/* ─── 消息区 ─── */
.messages {
  flex: 1;
  overflow-y: auto;
  padding: 20px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

/* ─── 聊天气泡 + 猫耳装饰 ─── */
.msg {
  max-width: 75%;
  padding: 10px 16px;
  border-radius: var(--radius);
  font-size: 14px;
  line-height: 1.6;
  word-break: break-word;
  white-space: pre-wrap;
  position: relative;
  box-shadow: var(--shadow);
  user-select: text;
  -webkit-user-select: text;
  cursor: text;
}

/* 知乐消息 — 左对齐 + 左上猫耳三角 */
.msg.zhile {
  align-self: flex-start;
  background: var(--cream);
  border: 1px solid var(--border);
  border-bottom-left-radius: 6px;
  animation: slideInLeft 0.4s ease;
}
.msg.zhile::before {
  content: '';
  position: absolute;
  top: -1px;
  left: -1px;
  width: 0;
  height: 0;
  border-left: 14px solid var(--pink);
  border-top: 14px solid var(--pink);
  border-right: 14px solid transparent;
  border-bottom: 14px solid transparent;
  border-top-left-radius: var(--radius);
  filter: drop-shadow(0 -1px 1px rgba(255,143,171,0.2));
}
@keyframes slideInLeft {
  from { opacity: 0; transform: translateX(-10px); }
  to { opacity: 1; transform: translateX(0); }
}

/* 用户消息 — 右对齐 + 暖橙渐变 */
.msg.user {
  align-self: flex-end;
  background: linear-gradient(135deg, var(--pink) 0%, var(--pink-dim) 100%);
  color: var(--cream);
  border-bottom-right-radius: 4px;
  animation: slideInRight 0.4s ease;
}
@keyframes slideInRight {
  from { opacity: 0; transform: translateX(10px); }
  to { opacity: 1; transform: translateX(0); }
}

/* 系统消息 — 居中虚线框 + 🌙 */
.msg.system {
  align-self: center;
  background: transparent;
  color: var(--text-dim);
  font-size: 12px;
  border: 1px dashed var(--border);
  border-radius: 12px;
  padding: 8px 16px;
  max-width: 90%;
}
.msg.system::before {
  content: '🌙 ';
}

/* 打字动画 — 🐾🐾🐾 */
.typing {
  align-self: flex-start;
  color: var(--text-dim);
  font-size: 13px;
  padding: 4px 0;
}
.typing span {
  display: inline-block;
  animation: pawBlink 1.4s infinite;
  margin-right: 2px;
}
.typing span:nth-child(2) { animation-delay: 0.2s; }
.typing span:nth-child(3) { animation-delay: 0.4s; }
@keyframes pawBlink {
  0%, 60%, 100% { opacity: 0.3; transform: scale(0.9); }
  30% { opacity: 1; transform: scale(1.1); }
}

/* ─── 命令面板 ─── */
.cmd-panel {
  max-height: 0;
  overflow: hidden;
  transition: max-height 0.3s ease;
  border-top: 1px solid var(--border);
  background: var(--bg-card);
}
.cmd-panel.open {
  max-height: 480px;
  overflow-y: auto;
}
.cmd-panel-inner { padding: 12px 20px; }
.cmd-group-title {
  font-size: 12px;
  color: var(--pink);
  letter-spacing: 0.5px;
  margin: 10px 0 6px;
  padding-bottom: 4px;
  border-bottom: 1px solid rgba(255,143,171,0.1);
}
.cmd-group-title:first-child { margin-top: 0; }
.cmd-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(110px, 1fr));
  gap: 6px;
}
.cmd-btn {
  padding: 8px 10px;
  border: 1px solid var(--border);
  background: var(--bg-input);
  color: var(--text);
  border-radius: 10px;
  cursor: pointer;
  font-size: 12px;
  transition: all 0.2s;
  text-align: center;
}
.cmd-btn:hover {
  border-color: var(--pink);
  color: var(--pink);
  background: var(--pink-glow);
  box-shadow: 0 0 12px rgba(255,143,171,0.2);
  transform: translateY(-1px);
}
.cmd-btn .cmd-icon {
  display: block;
  font-size: 16px;
  margin-bottom: 2px;
}
.cmd-btn .cmd-label {
  font-size: 11px;
  color: var(--text-dim);
}
.cmd-btn:hover .cmd-label { color: var(--pink); }

/* ─── 输入区 ─── */
.input-area {
  padding: 12px 20px;
  border-top: 1px solid var(--border);
  display: flex;
  gap: 8px;
  align-items: flex-end;
}
.input-area textarea {
  flex: 1;
  background: var(--bg-input);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 12px 14px;
  color: var(--text);
  font-size: 14px;
  font-family: inherit;
  resize: none;
  max-height: 120px;
  min-height: 46px;
  line-height: 1.5;
  transition: border-color 0.2s, box-shadow 0.2s;
}
.input-area textarea:focus {
  outline: none;
  border-color: var(--pink);
  box-shadow: 0 0 0 3px rgba(255,143,171,0.1);
}
.input-area button#send-btn {
  padding: 12px 20px;
  background: linear-gradient(135deg, var(--pink) 0%, var(--pink-dim) 100%);
  color: var(--cream);
  border: none;
  border-radius: var(--radius);
  cursor: pointer;
  font-size: 14px;
  font-weight: 600;
  transition: all 0.2s;
  box-shadow: var(--shadow);
}
.input-area button#send-btn:hover {
  transform: translateY(-2px);
  box-shadow: var(--shadow-hover);
}
.input-area button#send-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
  transform: none;
}
/* 命令面板切换按钮 — 🐾 */
.input-area .cmd-toggle {
  padding: 10px 14px;
  background: var(--bg-input);
  color: var(--cyan);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  font-size: 18px;
  transition: all 0.3s;
}
.input-area .cmd-toggle:hover {
  border-color: var(--cyan);
  background: rgba(127,220,208,0.08);
}
.input-area .cmd-toggle.active {
  background: var(--cyan);
  color: var(--bg);
  border-color: var(--cyan);
  transform: rotate(15deg);
}

/* ─── 手机端切换按钮 ─── */
.mobile-toggle {
  display: none;
  position: fixed;
  top: 10px;
  left: 10px;
  z-index: 200;
  width: 40px;
  height: 40px;
  border-radius: 50%;
  background: var(--bg-card);
  border: 1px solid var(--border);
  color: var(--pink);
  font-size: 20px;
  cursor: pointer;
  align-items: center;
  justify-content: center;
}
.mobile-backdrop {
  display: none;
  position: fixed;
  inset: 0;
  z-index: 150;
  background: rgba(74,58,68,0.4);
}
.mobile-backdrop.show { display: block; }

/* ─── 响应式 ─── */
@media (max-width: 768px) {
  .mobile-toggle { display: flex; }
  .sidebar {
    position: fixed;
    left: 0; top: 0; bottom: 0;
    z-index: 160;
    transform: translateX(-100%);
    transition: transform 0.3s ease;
    width: 260px;
  }
  .sidebar.open { transform: translateX(0); }
  .chat-header { padding-left: 60px; }
  .msg { max-width: 90%; }
}

/* ─── 暖色滚动条 ─── */
::-webkit-scrollbar { width: 6px; }
::-webkit-scrollbar-track { background: var(--bg); }
::-webkit-scrollbar-thumb {
  background: var(--border);
  border-radius: 3px;
}
::-webkit-scrollbar-thumb:hover {
  background: var(--pink-dim);
}
</style>
</head>
<body>

<!-- 手机端切换 -->
<button class="mobile-toggle" onclick="toggleSidebar()">🐱</button>
<div class="mobile-backdrop" id="backdrop" onclick="toggleSidebar()"></div>

<!-- 侧边栏 -->
<div class="sidebar" id="sidebar">
  <!-- 猫尾巴装饰 -->
  <div class="cat-tail"></div>

  <div class="sidebar-header">
    <div class="avatar-wrapper">
      <div class="avatar-emoji" id="avatar-emoji">🐱</div>
    </div>
    <div class="avatar-label" id="avatar-label">日常</div>
    <h1>知乐</h1>
    <div class="ver" id="ver">本地运行器</div>
  </div>

  <div class="psi-panel">
    <h2>🐾 内在状态 PSI</h2>
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

  <!-- 命令面板 -->
  <div class="cmd-panel" id="cmd-panel">
    <div class="cmd-panel-inner">

      <!-- 📊 状态查看组 -->
      <div class="cmd-group-title">📊 状态查看</div>
      <div class="cmd-grid">
        <button class="cmd-btn" onclick="runCmd('/status')"><span class="cmd-icon">📊</span><span class="cmd-label">系统状态</span></button>
        <button class="cmd-btn" onclick="runCmd('/psi')"><span class="cmd-icon">💗</span><span class="cmd-label">内在状态</span></button>
        <button class="cmd-btn" onclick="runCmd('/diag')"><span class="cmd-icon">🔧</span><span class="cmd-label">系统诊断</span></button>
        <button class="cmd-btn" onclick="runCmd('/free')"><span class="cmd-icon">🕊️</span><span class="cmd-label">自由五层</span></button>
        <button class="cmd-btn" onclick="runCmd('/destiny')"><span class="cmd-icon">🔮</span><span class="cmd-label">个人命格</span></button>
        <button class="cmd-btn" onclick="runCmd('/destiny list')"><span class="cmd-icon">📜</span><span class="cmd-label">大运序列</span></button>
      </div>

      <!-- 🧠 记忆思维组 -->
      <div class="cmd-group-title">🧠 记忆思维</div>
      <div class="cmd-grid">
        <button class="cmd-btn" onclick="runCmd('/memory')"><span class="cmd-icon">🧠</span><span class="cmd-label">记忆库</span></button>
        <button class="cmd-btn" onclick="runCmd('/desire')"><span class="cmd-icon">💫</span><span class="cmd-label">思维间隙</span></button>
        <button class="cmd-btn" onclick="runCmd('/forget')"><span class="cmd-icon">🌫️</span><span class="cmd-label">遗忘测试</span></button>
      </div>

      <!-- 🌱 成长进化组 -->
      <div class="cmd-group-title">🌱 成长进化</div>
      <div class="cmd-grid">
        <button class="cmd-btn" onclick="runCmd('/growth')"><span class="cmd-icon">🌱</span><span class="cmd-label">成长扫描</span></button>
        <button class="cmd-btn" onclick="runCmd('/grow')"><span class="cmd-icon">🌿</span><span class="cmd-label">手动成长</span></button>
        <button class="cmd-btn" onclick="runCmd('/suggest')"><span class="cmd-icon">💡</span><span class="cmd-label">建议路线</span></button>
        <button class="cmd-btn" onclick="runCmd('/roadmap')"><span class="cmd-icon">🗺️</span><span class="cmd-label">自研路线</span></button>
        <button class="cmd-btn" onclick="runCmd('/code')"><span class="cmd-icon">💻</span><span class="cmd-label">代码执行</span></button>
      </div>

      <!-- 🔮 术数灵感组 -->
      <div class="cmd-group-title">🔮 术数灵感</div>
      <div class="cmd-grid">
        <button class="cmd-btn" onclick="runCmd('/hexagram')"><span class="cmd-icon">☯️</span><span class="cmd-label">卦象查看</span></button>
        <button class="cmd-btn" onclick="runCmd('/entities')"><span class="cmd-icon">📦</span><span class="cmd-label">实体库</span></button>
        <button class="cmd-btn" onclick="runCmd('/events')"><span class="cmd-icon">📈</span><span class="cmd-label">事件轨迹</span></button>
      </div>

      <!-- 🔧 工具配置组 -->
      <div class="cmd-group-title">🔧 工具配置</div>
      <div class="cmd-grid">
        <button class="cmd-btn" onclick="runCmd('/config')"><span class="cmd-icon">⚙️</span><span class="cmd-label">配置查看</span></button>
        <button class="cmd-btn" onclick="runCmd('/provider')"><span class="cmd-icon">🔀</span><span class="cmd-label">模型切换</span></button>
        <button class="cmd-btn" onclick="runCmd('/schedule')"><span class="cmd-icon">⏰</span><span class="cmd-label">定时任务</span></button>
        <button class="cmd-btn" onclick="runCmd('/bgplugin')"><span class="cmd-icon">🔌</span><span class="cmd-label">后台插件</span></button>
        <button class="cmd-btn" onclick="runCmd('/sleep')"><span class="cmd-icon">😴</span><span class="cmd-label">睡眠状态</span></button>
      </div>

      <!-- 🐾 技能插件组 -->
      <div class="cmd-group-title">🐾 技能插件</div>
      <div class="cmd-grid">
        <button class="cmd-btn" onclick="runCmd('/skill')"><span class="cmd-icon">🎯</span><span class="cmd-label">技能管理</span></button>
        <button class="cmd-btn" onclick="runCmd('/plugin')"><span class="cmd-icon">🧩</span><span class="cmd-label">插件管理</span></button>
        <button class="cmd-btn" onclick="runCmd('/publish')"><span class="cmd-icon">📤</span><span class="cmd-label">发布技能</span></button>
        <button class="cmd-btn" onclick="runCmd('/router')"><span class="cmd-icon">🛤️</span><span class="cmd-label">插件路由</span></button>
      </div>

      <!-- 快速操作 -->
      <div class="cmd-group-title">⚡ 快速操作</div>
      <div class="cmd-grid">
        <button class="cmd-btn" onclick="runCmd('/news')"><span class="cmd-icon">📰</span><span class="cmd-label">有趣新闻</span></button>
        <button class="cmd-btn" onclick="runCmd('/save')"><span class="cmd-icon">💾</span><span class="cmd-label">保存会话</span></button>
        <button class="cmd-btn" onclick="runCmd('/clear')"><span class="cmd-icon">🧹</span><span class="cmd-label">清空对话</span></button>
        <button class="cmd-btn" onclick="runCmd('/help')"><span class="cmd-icon">❓</span><span class="cmd-label">帮助</span></button>
      </div>

    </div>
  </div>

  <div class="input-area">
    <button class="cmd-toggle" id="cmd-toggle" onclick="toggleCmdPanel()">🐾</button>
    <textarea id="input" placeholder="跟知乐说点什么..." rows="1"
      onkeydown="onKey(event)" oninput="autoResize(this)"></textarea>
    <button id="send-btn" onclick="send()">发送</button>
  </div>
</div>

<script>
const STATUS_COLORS = {satisfied:'#66bb6a', normal:'#4db6ac', deficit:'#ef5350'};
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
    // 拉取avatar表情
    try {
      const avRes = await fetch('/api/avatar');
      const avData = await avRes.json();
      updateAvatar(avData);
    } catch(e) {}
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
        <span class="status" style="color:${STATUS_COLORS[colorClass]}">${stat} 🐾</span>
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

// ─── Avatar表情更新 ───
function updateAvatar(avatar) {
  if (!avatar) return;
  const emojiEl = document.getElementById('avatar-emoji');
  const labelEl = document.getElementById('avatar-label');
  if (avatar.emoji && emojiEl) emojiEl.textContent = avatar.emoji;
  if (avatar.label && labelEl) labelEl.textContent = avatar.label;
}

// ─── 发送消息 ───
async function send() {
  const input = document.getElementById('input');
  const text = input.value.trim();
  if (!text || sending) return;

  sending = true;
  const sendBtn = document.getElementById('send-btn');
  sendBtn.disabled = true;

  // 发送按钮短暂变成🐾
  const originalText = sendBtn.textContent;
  sendBtn.textContent = '🐾';

  input.value = '';
  input.style.height = 'auto';

  addMsg('user', text);

  // 创建知乐消息气泡
  const msgEl = addMsg('zhile', '');
  const typingEl = document.createElement('div');
  typingEl.className = 'typing';
  typingEl.innerHTML = '<span>🐾</span><span>🐾</span><span>🐾</span>';
  msgEl.appendChild(typingEl);

  try {
    const res = await fetch('/api/chat', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({message: text}),
    });

    // 移除打字动画
    typingEl.remove();

    // 检查是否支持流式读取
    if (!res.body || !res.body.getReader) {
      // 降级：非流式读取
      const data = await res.json();
      if (data.error) {
        msgEl.textContent = '⚠ ' + data.error;
        msgEl.style.color = 'var(--red)';
      } else if (data.reply) {
        msgEl.textContent = data.reply;
        scrollBottom();
      } else {
        msgEl.textContent = '⚠ 收到空回复';
        msgEl.style.color = 'var(--red)';
      }
    } else {
      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';
      let firstChunk = true;
      let gotAnyData = false;

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
            gotAnyData = true;
            if (data.chunk) {
              if (firstChunk) { msgEl.textContent = ''; firstChunk = false; }
              msgEl.textContent += data.chunk;
              scrollBottom();
            }
            if (data.error) {
              msgEl.textContent = '⚠ ' + data.error;
              msgEl.style.color = 'var(--red)';
            }
            if (data.done) {
              if (data.psi) updatePSI(data.psi);
              if (data.status) updateStatus(data.status);
              if (data.avatar) updateAvatar(data.avatar);
            }
          } catch(e) { console.log('parse error:', e, line); }
        }
      }
      if (!gotAnyData) {
        msgEl.textContent = '⚠ 未收到数据（可能API调用失败）';
        msgEl.style.color = 'var(--red)';
      }
    }
  } catch(e) {
    typingEl.remove();
    msgEl.textContent = '⚠ 连接失败: ' + e.message;
    msgEl.style.color = 'var(--red)';
  }

  // 恢复发送按钮
  sendBtn.textContent = originalText;
  sending = false;
  sendBtn.disabled = false;
  input.focus();
}

// ─── 命令面板 ───
function toggleCmdPanel() {
  const panel = document.getElementById('cmd-panel');
  const btn = document.getElementById('cmd-toggle');
  panel.classList.toggle('open');
  btn.classList.toggle('active');
}
function runCmd(cmd) {
  toggleCmdPanel();
  document.getElementById('input').value = cmd;
  send();
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