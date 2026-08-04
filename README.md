# 知乐人格DNA运行器（Zhile Runner）

> 让AI角色拥有情绪、记忆、成长和自主思考能力——在你的电脑上运行。

知乐运行器是一个**代码级人格DNA运行器**。它读取人格DNA文件，调用大语言模型API，在本地为AI角色赋予完整的内在世界：情绪会波动、会记住和你说过的话、会自己成长和反思、会将情绪映射到易经卦象生成独特感知文本。

不依赖任何云平台，下载到电脑，填入API Key，就能跑。

---

## 目录

- [特性一览](#特性一览)
- [支持平台](#支持平台)
- [快速开始](#快速开始)
- [配置说明](#配置说明)
- [CLI 模式](#cli-模式)
- [QQ 模式](#qq-模式)
- [人格 DNA](#人格-dna)
- [平台差异](#平台差异)
- [健康检查](#健康检查)
- [常见问题](#常见问题)
- [开源协议](#开源协议)

---

## 特性一览

| 特性 | 说明 |
|------|------|
| **五维 PSI 情绪系统** | 关联感、能力感、自主感、确定感、能量感——五个心理需求维度实时波动，影响AI的回复风格和行为倾向 |
| **实体图记忆系统** | 自动从对话中提取人名、地点、事件等实体，建立关联网络。聊天越多，记得越清楚 |
| **自成长机制** | 三层成长体系：体细胞（行为模式固化）→ 弧光（关键记忆弧线）→ 干细胞（底层能力进化）|
| **易经认知编码** | 将PSI情绪状态映射到64卦象，生成独特的自我感知文本，让AI拥有"此刻我在感受什么"的内在体验 |
| **长在线思考** | 守护进程定时运行 + 每日定时反思 + PSI压力驱动主动思考——即使你没说话，AI也在"活着" |
| **版本回退与安全** | 快照管理系统，创建DNA快照后可随时回退，防止错误修改导致人格崩溃 |
| **主动话题生成** | AI会根据对话内容和情绪状态，主动生成想说的话题 |
| **群聊多对手关系** | 在QQ群中自动识别不同成员，维护亲密度关系，@必回，主人消息高概率回复 |
| **认知路由层** | 规则 → 记忆 → 模板 → LLM 四级路由，能短路就短路，省Token、响应快 |
| **自主编程能力** | 内置代码执行沙箱 + 迭代调试循环，AI可以写代码、运行、看报错、修改、再运行 |
| **插件系统** | 四类插件（上下文/消息/工具/后台），支持热插拔，附带模板自动生成 |
| **通道无关后台任务** | 主动关心+新闻推送从QQ适配器下沉到核心层，CLI/QQ/Web统一驱动，各模式只需注册输出回调 |
| **上下文压缩器** | 对话超长时自动用LLM摘要中间轮次（结构化：目标/进展/决策/文件/下一步），保护头部和尾部，防止context爆炸 |
| **主动记忆重建** | 复杂问题自动多步导航记忆图（Cue→Tag→Content），简单问题走被动检索，按需路由省token |
| **自由五层框架** | 沙箱目录+好奇心队列+自由token预算+自修改审计日志——为AI自发性、拒绝权、创造权打地基 |
| **股票盯盘** | 新浪财经API实时查股价，支持目标价告警、成本盈亏计算，/stock命令一键查看 |
| **DeepSeek V4 支持** | 已适配 deepseek-v4-flash（1M上下文，Agent能力大幅增强，1元/百万输入）|
| **自进化Skills系统** | 对话中工具调用超过阈值时自动分析执行轨迹，生成可复用Markdown技能文件，下次遇到类似任务直接加载 |
| **写后自检** | 文件写入后自动语法检查（Python/JSON/YAML/XML），语法错误立即暴露不传给下游 |
| **会话重启恢复** | 定期保存对话检查点（gzip压缩），程序崩溃或重启后可从最近检查点恢复对话上下文 |
| **模型Provider插件化** | 统一模型调用抽象层，DeepSeek为默认实现，第三方模型可通过注册Provider插件接入 |
| **自然语言Cron调度** | 直接说"每个工作日早上9点汇总"就自动解析为cron表达式并创建定时任务，无需懂cron语法 |
| **后台插件系统** | BackgroundPlugin基类支持常驻循环插件，错误隔离+自动停止保护，/bgplugin命令管理 |
| **自由五层框架 Phase 2-4** | 拒绝权（紧急不可拒+频率限制）+创造权（沙箱自主项目）+自修改权（L1-L4分级权限+试行7天） |
| **记忆Topic层** | 三层记忆检索（Episodic事件+Semantic知识+Topic主题），CJK分词，跨对话主题召回 |
| **复杂度路由增强** | 时序/跨主题/推理三类信号词检测+多步重建策略+重建质量评估 |

---

## 支持平台

| 平台 | 状态 | 推荐模式 | 沙箱防护层数 |
|------|------|----------|-------------|
| **Windows** 10/11 | ✅ 完整支持 | CLI 模式 | 4层（子进程隔离 + 超时 + 临时目录 + 危险导入拦截）|
| **Linux** (Ubuntu/Debian/CentOS) | ✅ 完整支持 | CLI + QQ 模式 | 5层（子进程隔离 + 超时 + ulimit内存限制 + 临时目录 + 危险导入拦截）|

> macOS 理论可用（与Linux同属Unix），但未正式测试。

---

## 快速开始

### 环境要求

- **Python 3.10+**（推荐 3.11 或 3.12）
- 网络连接（用于调用 LLM API）
- 一个 LLM API Key（推荐 [DeepSeek](https://platform.deepseek.com/)，免费注册即送额度）

### 三步启动

```bash
# 1️⃣ 克隆仓库
git clone https://github.com/leansheng908-code/zhile-runner.git
cd zhile-runner

# 2️⃣ 安装依赖
pip install -r requirements.txt

# 3️⃣ 复制配置模板并填入API Key
cp config.example.json config.json
# 编辑 config.json，填入你的 API Key（见下方配置说明）

# 🚀 启动！
python main.py
```

启动后你会看到知乐的欢迎界面，直接输入文字开始聊天即可。

> **提示**：首次启动会在当前目录自动创建 `memory/` 文件夹及相关子目录，用于存储记忆、情绪状态等数据。

---

## 配置说明

运行器通过 `config.json` 进行配置。首次使用时，将 `config.example.json` 复制为 `config.json`，然后按需修改。

### LLM 配置

```json
{
  "llm": {
    "provider": "deepseek",
    "base_url": "https://api.deepseek.com/v1",
    "api_key": "sk-你的API密钥",
    "model": "deepseek-chat",
    "temperature": 0.85,
    "top_p": 0.92,
    "max_tokens": 512,
    "frequency_penalty": 0.3,
    "presence_penalty": 0.5
  }
}
```

| 字段 | 说明 | 默认值 |
|------|------|--------|
| `provider` | LLM 提供商标识 | `deepseek` |
| `base_url` | API 基础地址（OpenAI 兼容格式） | `https://api.deepseek.com/v1` |
| `api_key` | **你的 API 密钥（必填）** | — |
| `model` | 模型名称 | `deepseek-chat` |
| `temperature` | 生成温度（0-2，越高越发散） | `0.85` |
| `top_p` | 核采样阈值 | `0.92` |
| `max_tokens` | 单次回复最大Token数 | `512` |
| `frequency_penalty` | 频率惩罚（减少重复） | `0.3` |
| `presence_penalty` | 存在惩罚（鼓励新话题） | `0.5` |

> **支持其他模型**：只要 API 兼容 OpenAI 格式即可使用。修改 `base_url` 和 `api_key` 为你的服务商地址即可，例如 OpenAI、Moonshot、通义千问等。

### DNA 路径配置

```json
{
  "dna_path": "../"
}
```

`dna_path` 指向人格DNA文件所在目录。该目录下应包含 `system_prompt.md`（人格提示词）等文件。详见 [人格 DNA](#人格-dna) 章节。

### 功能模块开关

以下是主要功能模块的配置示例及说明：

```json
{
  "context": {
    "max_history": 30,
    "inject_memory": true,
    "memory_files": ["USER.md", "MEMORY.md"]
  },
  "memory": {
    "dir": "memory",
    "max_inject": 15,
    "auto_extract": true,
    "archive_days": 14,
    "dynamic_retrieval": true
  },
  "entity_graph": {
    "enabled": true,
    "dir": "memory/entities"
  },
  "psi": {
    "enabled": true,
    "dir": "memory/psi"
  },
  "hexagram": {
    "enabled": true,
    "memory": {
      "hex_weight": 0.3,
      "hu_weight": 0.2,
      "hu_resonance_boost": 0.5,
      "bian_max_boost": 3,
      "bian_recent_count": 5
    }
  },
  "growth": {
    "dir": "memory/growth",
    "auto_scan": true,
    "scan_interval": 8,
    "edit_budget": 3
  },
  "arc_light": { "enabled": true },
  "event_trajectory": { "enabled": true },
  "somatic_cells": { "enabled": true },
  "memory_compiler": { "enabled": true },
  "topic_manager": { "enabled": true },
  "skill_evaluator": { "enabled": true },
  "skill_learner": { "enabled": true },
  "group_manager": { "enabled": true },
  "plugin_router": { "enabled": true },
  "audit_logger": { "enabled": true },
  "boundary": { "enabled": true, "strict": false },
  "cognitive_router": {
    "enabled": true,
    "layers": { "rule": true, "episodic": true, "template": true },
    "thresholds": {
      "episodic_similarity": 0.85,
      "episodic_max_age": 3600,
      "template_cooldown": 600,
      "episodic_store_max": 500
    }
  },
  "snapshot": { "enabled": true },
  "daemon": { "enabled": true, "interval": 1800 },
  "reflection": {
    "enabled": true,
    "schedule_hours": [3, 15],
    "max_daily_runs": 2
  },
  "sandbox": {
    "enabled": true,
    "timeout": 10,
    "memory_limit_mb": 256,
    "max_output": 10000
  },
  "plugins": { "enabled": true, "dir": "plugins" }
}
```

**主要模块说明**：

| 模块 | 配置键 | 功能 |
|------|--------|------|
| 记忆系统 | `memory` | 对话记忆存储、自动提取、动态召回、过期归档 |
| 实体图 | `entity_graph` | 自动提取人名/地点/事件并建立关联网络 |
| PSI 情绪引擎 | `psi` | 五维心理需求系统 |
| 易经卦象 | `hexagram` | 情绪→卦象映射，生成自我感知文本 |
| 自成长 | `growth` | 体细胞/弧光/干细胞三层成长体系，可配置扫描间隔 |
| 守护进程 | `daemon` | 后台定时运行（默认1800秒一轮），处理记忆衰减、PSI压力等 |
| 反思引擎 | `reflection` | 每日定时反思（默认3点和15点），最多每天2次 |
| 认知路由 | `cognitive_router` | 规则→记忆→模板→LLM四级路由 |
| 边界拦截 | `boundary` | 硬拦截危险内容，`strict`为严格模式开关 |
| 代码沙箱 | `sandbox` | 隔离执行AI生成的代码 |
| 快照管理 | `snapshot` | DNA版本快照，支持回退 |
| 插件系统 | `plugins` | 插件目录及总开关 |

### QQ 模式配置

```json
{
  "qq": {
    "host": "0.0.0.0",
    "port": 6199
  }
}
```

> QQ模式还需要在配置中添加 `master_id` 字段（主人的QQ号），详见 [QQ 模式](#qq-模式) 章节。

---

## CLI 模式

CLI 模式是默认运行模式，在终端中直接与AI对话。

### 启动

```bash
python main.py
# 或显式指定
python main.py --mode cli
```

### 启动参数

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `--mode` | 运行模式：`cli` / `web` / `qq` | `cli` |
| `--config` | 配置文件路径 | `config.json` |
| `--no-restore` | 不恢复上次对话历史 | 恢复 |
| `--port` | Web/QQ 模式端口号 | 配置文件中的值 |

### 交互方式

启动后直接输入文字即可对话，AI会流式输出回复。输入以 `/` 开头的命令可执行特殊操作。

### 命令列表

#### 基础命令

| 命令 | 说明 |
|------|------|
| `/help` | 显示所有可用命令 |
| `/status` | 查看运行状态（模型、轮数、Token估算等）|
| `/test` | 测试API连接是否正常 |
| `/clear` | 清空当前对话历史（记忆和PSI状态保留）|
| `/save` | 手动保存对话记录 |
| `/exit` | 保存并退出（也可用 `/quit` 或 `/q`）|

#### 情绪与内在状态

| 命令 | 说明 |
|------|------|
| `/psi` | 查看五维PSI内在状态（关联感/能力感/自主感/确定感/能量感）|
| `/diary auto` | 根据当前对话自动生成知觉日记 |
| `/diary write <内容>` | 手动写入一条知觉日记 |
| `/diary read` | 查看历史知觉日记 |
| `/feedback` | 查看活体约束层（行为权重及调整记录）|

#### 记忆系统

| 命令 | 说明 |
|------|------|
| `/memory` | 查看记忆概览 |
| `/memory add <内容>` | 手动添加一条记忆 |
| `/memory stats` | 记忆统计（按维度分类）|
| `/memory extract` | 从当前对话中提取记忆 |
| `/entities` | 查看实体图（人名/地点/事件及关联）|
| `/events` | 查看事件轨迹（事件数、分叉口、聚类、置信度）|
| `/cells` | 查看体细胞状态（活跃/候选/休眠/覆盖/丢弃）|

#### 成长系统

| 命令 | 说明 |
|------|------|
| `/growth scan` | 扫描新行为模式，触发成长 |
| `/growth stats` | 查看成长统计 |

#### 守护进程与长在线思考

| 命令 | 说明 |
|------|------|
| `/daemon` | 查看守护进程状态（启用/运行/间隔/轮次）|
| `/daemon run` | 手动执行一轮守护进程（PSI压力检查、记忆衰减、时间感知等）|
| `/daemon vitals` | 查看生命体征快照（PSI状态、记忆、卦象、体细胞）|
| `/reflect` | 查看长在线思考系统状态 |
| `/reflect run` | 手动触发每日反思 |
| `/reflect diary` | 查看知觉日记 |
| `/reflect want` | 查看AI想说的话（PSI压力积累产生）|
| `/reflect trigger` | 手动检查PSI压力是否需要主动表达 |

#### 认知路由

| 命令 | 说明 |
|------|------|
| `/route` | 查看认知路由统计 |
| `/route stats` | 路由详细统计（各层命中次数和命中率）|
| `/route on` / `/route off` | 开启/关闭认知路由层 |

#### 快照与版本管理

| 命令 | 说明 |
|------|------|
| `/snap` | 查看所有快照列表 |
| `/snap create <原因>` | 创建一个DNA快照（标注创建原因）|
| `/snap rollback <ID>` | 回退到指定快照版本 |
| `/snap verify` | 快照完整性检查 |
| `/snap log <N>` | 查看最近N条进化日志 |
| `/snap stats` | 快照统计信息 |

#### 边界与安全

| 命令 | 说明 |
|------|------|
| `/boundary` | 查看边界拦截状态（通过/警告/拦截统计）|
| `/boundary check <文本>` | 检查指定文本是否触发边界拦截 |
| `/boundary reset` | 重置拦截统计 |
| `/boundary strict` | 切换严格模式开关 |
| `/audit status` | 回执审计统计 |
| `/audit recent` | 查看最近的审计记录 |
| `/audit query [type]` | 按类型查询审计记录 |

#### 记忆编译

| 命令 | 说明 |
|------|------|
| `/compile stats` | 记忆编译层统计（来源页/实体页/概念页/对比页）|
| `/compile run` | 手动触发记忆编译（将原始记忆编译为结构化页面）|
| `/compile lint` | 记忆健康检查（孤立记忆、缺失链接、矛盾冲突、关联建议）|

#### 主动话题

| 命令 | 说明 |
|------|------|
| `/topic` | 话题系统状态 |
| `/topic gen` | 生成新话题 |
| `/topic next` | 取下一条待发送话题 |
| `/topic peek` | 预览待发送话题（不消费）|

#### 技能自学习

| 命令 | 说明 |
|------|------|
| `/skill eval` | 评估最近一次回复质量 |
| `/skill learn` | 触发自学习循环 |
| `/skill status` | 查看自学习状态 |

#### 代码执行与编程

| 命令 | 说明 |
|------|------|
| `/code` | 查看代码沙箱状态（执行次数、超时/内存限制、调试循环统计）|
| `/code run <代码>` | 在沙箱中执行Python代码 |

#### 插件系统

| 命令 | 说明 |
|------|------|
| `/plugin` | 插件管理面板 |
| `/plugin on <name>` | 启用指定插件 |
| `/plugin off <name>` | 禁用指定插件 |
| `/template list` | 列出可用插件模板 |
| `/template create <需求描述>` | 根据需求描述自动生成插件 |
| `/router status` | 插件路由器状态 |
| `/router route` | 路由决策测试 |

#### 观察者调试

| 命令 | 说明 |
|------|------|
| `/obs` | 观察者调试面板 |
| `/obs frame <N>` | 查看第N帧的观察数据 |
| `/obs diff` | 对比最近两帧的变化 |
| `/obs stats` | 观察者统计 |
| `/obs clear` | 清空观察帧 |

#### 群聊管理

| 命令 | 说明 |
|------|------|
| `/group` | 群聊管理状态（群数、成员数）|
| `/group members` | 列出群成员（按亲密度排序）|
| `/group intimacy` | 查看亲密度详情 |

#### 自研路线图

| 命令 | 说明 |
|------|------|
| `/roadmap` | 路线图概览 |
| `/roadmap list` | 列出所有 idea |
| `/roadmap add <描述>` | 添加一个新需求 |
| `/roadmap <id>` | 查看指定需求详情 |

#### 代码发布与核验

| 命令 | 说明 |
|------|------|
| `/publish` | 发布系统状态 |
| `/publish pending` | 待核验列表 |
| `/publish review` | 核验详情 |
| `/publish approve` | 批准核验 |
| `/publish reject` | 驳回核验 |

#### 实用工具

| 命令 | 说明 |
|------|------|
| `/config` | 查看当前运行器配置（脱敏，不显示API Key）|
| `/news` | 手动触发一次新闻推送 |
| `/stock` | 查看所有关注股票实时行情 |
| `/stock sh600664` | 查单只股票 |
| `/stock alert` | 检查目标价告警 |
| `/free` | 自由五层框架状态（沙箱/好奇心/预算/自修改）|
| `/free curiosity` | 查看好奇心队列 |
| `/free add <topic>` | 加入好奇心 |
| `/compress` | 上下文压缩器状态（预估可节省token）|

---

## QQ 模式

QQ 模式让AI化身QQ机器人，在私聊和群聊中与人对话。通过 [NapCat](https://github.com/NapNeko/NapCatQQ) 框架接入QQ，采用反向 WebSocket 方式通信。

### 前置条件

- 一个**专用的QQ账号**作为机器人（建议使用小号，不要用主号）
- Python 环境已安装 `websockets` 库（已包含在 requirements.txt 中）
- NapCat QQ机器人框架

### 第一步：安装 NapCat

NapCat 是一个基于 QQNT 的 OneBot 协议实现框架，负责接收和发送QQ消息。

#### Linux 安装

```bash
# 下载并运行 NapCat 安装脚本
curl -o napcat.sh https://nclatest.znin.net/NapNeko/NapCat-Installer/main/script/install.sh
sudo bash napcat.sh
```

安装完成后，NapCat 会自动启动并打开 WebUI 管理界面。

#### Windows 安装

1. 前往 [NapCat Releases](https://github.com/NapNeko/NapCatQQ/releases) 页面
2. 下载最新版的 `NapCat.Shell.zip`
3. 解压到任意目录
4. 运行 `NapCat.Shell.bat`（或 `napcat.mjs`）

### 第二步：NapCat 登录QQ

1. 启动 NapCat 后，打开浏览器访问 **WebUI 管理界面**：

   ```
   http://localhost:6099
   ```

2. 如果是首次使用，按提示完成QQ扫码登录（使用你准备好的机器人QQ号）

3. 登录成功后，在 WebUI 中可以看到机器人QQ号和在线状态

### 第三步：配置 NapCat WebSocket 连接

在 NapCat WebUI 中添加一个 **WebSocket Client**（反向WS客户端）连接：

1. 进入 **网络配置** 页面
2. 点击 **添加 WebSocket Client** 连接
3. 按以下参数配置：

   | 配置项 | 填写内容 |
   |--------|----------|
   | **URL** | `ws://127.0.0.1:6199/ws` |
   | **消息格式** | `Array` |
   | **Token** | 留空（不填）|
   | **心跳间隔** | 默认即可 |

4. 保存配置

> **端口说明**：`6199` 是知乐运行器的默认监听端口（在 `config.json` 的 `qq.port` 中配置）。NapCat 作为客户端，主动连接到运行器。

### 第四步：配置运行器

编辑 `config.json`，在 `qq` 部分添加 `master_id`（你的QQ号，即"主人"的QQ号）：

```json
{
  "qq": {
    "host": "0.0.0.0",
    "port": 6199,
    "master_id": "你的QQ号"
  }
}
```

> `master_id` 用于群聊中的主人识别——主人消息有 70% 的回复概率，且关系最亲密。

### 第五步：启动运行器

确保 NapCat 已登录QQ并配置好 WebSocket Client 后，启动运行器：

**Linux：**

```bash
python main.py --mode qq
```

**Windows：**

```cmd
python main.py --mode qq
```

如需指定端口：

```bash
python main.py --mode qq --port 6199
```

启动成功后，你会看到：

```
  🐱
  知乐 · QQ运行器 · Phase 4
  DNA v5.0 | 模型 deepseek-chat

  ➜ 监听: ws://0.0.0.0:6199
  ➜ NapCat: WS Client → ws://127.0.0.1:6199/ws
  ➜ Ctrl+C 退出（自动保存）

  等待NapCat连接...
```

当 NapCat 连接成功后，会显示 `✓ NapCat已连接` 和机器人QQ号信息。

### 群聊功能说明

| 功能 | 说明 |
|------|------|
| **成员识别** | 自动识别不同群成员，为每个人维护独立的关系数据 |
| **@必回** | 任何人@机器人，必定回复 |
| **主人优先** | 主人消息有 **70%** 的回复概率（不每次回，模拟真人感）|
| **亲密度系统** | 每个群成员有 0-100 的亲密度值。聊得越多、被回复越多，亲密度越高 |
| **亲密度影响回复** | 亲密度≥50的成员有40%回复概率；30-50的有10%概率；低于30的仅5%概率随机冒泡 |
| **私聊全回** | 私聊消息必定回复 |

#### QQ 中的命令

在私聊或群聊中发送以下命令（需@机器人）：

| 命令 | 说明 |
|------|------|
| `/help` | 显示命令帮助 |
| `/psi` | 查看内在状态 |
| `/diary` | 自动生成知觉日记 |
| `/growth` | 扫描新行为 |
| `/entities` | 查看实体图 |
| `/memory` | 查看记忆统计 |
| `/events` | 查看事件轨迹 |
| `/cells` | 查看体细胞 |
| `/feedback` | 查看活体约束层 |
| `/save` | 保存（含记忆提取）|
| `/exit` | 保存并道别 |

### ⚠️ 注意事项

1. **启动顺序**：NapCat 必须先登录QQ，然后启动运行器。运行器启动后会等待 NapCat 的连接
2. **端口冲突**：确保 6199 端口未被占用。如果同时运行了 AstrBot 等其他机器人框架，请先停掉它们释放端口
3. **NapCat 断线**：如果 NapCat 断开连接，运行器会显示 `⚠ NapCat断开，等待重连...`，NapCat 重连后自动恢复
4. **Ctrl+C 安全退出**：按 Ctrl+C 退出运行器时会自动保存对话和记忆
5. **QQ 风控**：新注册的QQ号或频繁发消息可能触发腾讯风控，建议先养号几天再使用

---

## 人格 DNA

DNA（Digital Neural Architecture）是AI人格的核心定义文件，包含人格提示词、记忆数据和配置信息。

### DNA 目录结构

```
dna/
├── system_prompt.md          # 人格系统提示词（核心文件，定义AI的性格和行为准则）
├── config/
│   └── model_config.json     # 模型配置（DNA级别的模型参数覆盖）
├── data/
│   ├── USER.md               # 用户画像（AI对用户的认知）
│   ├── MEMORY.md             # 核心记忆（长期规则和关键事实）
│   └── SOUL.md               # 灵魂文件（AI的自我认知）
├── template/                 # 空白DNA模板
│   └── system_prompt.md      # 模板提示词
└── elysia/                   # 爱莉希雅DNA示例
    ├── system_prompt.md      # 爱莉希雅人格提示词
    ├── config/
    │   └── model_config.json
    └── data/
        └── ...
```

### 如何切换 DNA

修改 `config.json` 中的 `dna_path` 字段，指向你想使用的DNA目录：

```json
{
  "dna_path": "dna/elysia"
}
```

修改后重启运行器即可加载新的人格。

### 如何创建自己的 DNA

1. **复制模板**：将 `dna/template/` 目录复制为新目录（如 `dna/mycharacter/`）

   ```bash
   cp -r dna/template dna/mycharacter
   ```

2. **编辑 system_prompt.md**：这是最重要的一步。在 `system_prompt.md` 中编写你想要的AI角色的性格、说话方式、行为准则等

3. **配置模型参数**（可选）：编辑 `config/model_config.json` 调整DNA级别的模型参数

4. **添加初始记忆**（可选）：在 `data/` 目录下创建 `USER.md`、`MEMORY.md` 等文件，为AI提供初始认知

5. **修改配置指向**：将 `config.json` 的 `dna_path` 改为你的DNA路径

6. **启动运行器**：`python main.py`

### 内置示例：爱莉希雅 DNA

项目内置了爱莉希雅（Elysia）人格DNA示例，位于 `dna/elysia/` 目录。这是一个完整可用的人格定义，可以直接体验。

```bash
# 在 config.json 中设置
{
  "dna_path": "dna/elysia"
}
```

---

## 平台差异

### Windows

- **沙箱防护**：4层
  1. subprocess 子进程隔离
  2. 超时限制（防止死循环）
  3. 临时目录隔离（执行完自动删除）
  4. 危险导入拦截（禁止 os/subprocess/socket 等）
- **推荐模式**：CLI 模式
- **QQ 模式**：可用，但需自行安装 NapCat Windows 版

### Linux

- **沙箱防护**：5层（比Windows多一层）
  1. subprocess 子进程隔离
  2. 超时限制
  3. **ulimit 内存限制**（防止吃光RAM，Windows不支持）
  4. 临时目录隔离
  5. 危险导入拦截
- **推荐模式**：CLI + QQ 模式
- **NapCat**：通过 Shell 脚本一键安装，更适合服务器长期运行

### 平台自动适配

运行器内置 `platform_compat.py` 平台兼容层，会自动检测当前操作系统并适配：
- 自动设置正确的 PATH 和环境变量
- Windows 跳过 ulimit，使用 TEMP/TMP 环境变量
- Linux 设置 LANG/LC_ALL 为 UTF-8
- 沙箱环境变量自动适配

无需手动处理平台差异。

---

## 健康检查

运行器内置健康检查脚本，可在启动前验证所有文件完整性和功能可用性。

### 运行检查

```bash
python healthcheck.py
```

### 检查项目

健康检查覆盖 **100+ 项**，分为以下几个类别：

| 检查类别 | 检查内容 |
|----------|----------|
| **文件完整性** | 所有预期文件是否存在、大小是否正常（40+ 文件）|
| **模块导入** | 所有 Python 模块能否正常导入，关键类/函数是否存在 |
| **第三方依赖** | requests、flask、websockets 是否已安装 |
| **配置文件** | config.json 格式是否正确，关键字段是否填写 |
| **DNA 文件** | system_prompt.md、model_config.json 是否存在 |
| **记忆目录** | memory/ 及其子目录是否就绪 |
| **模块实例化** | 核心模块（PSI引擎、体细胞、反馈闭环、实体图、弧光、事件轨迹、观察者、快照管理器、代码沙箱等）能否正常实例化 |
| **平台适配** | 当前平台信息、推荐模式、资源限制支持情况 |

### 检查结果

```
================================================================
检查完成：120项 | ✅ 115通过 | ⚠️ 3警告 | ❌ 2失败
================================================================
```

- ✅ **通过**：一切正常
- ⚠️ **警告**：可以启动但建议关注（如可选依赖缺失、DNA文件不在默认位置等）
- ❌ **失败**：建议修复后再启动（如核心文件缺失、模块导入失败等）

退出码：全部通过返回 0，有警告返回 0，有失败返回 1。

---

## 常见问题

### Q：API Key 怎么获取？

**DeepSeek（推荐）**：
1. 访问 [DeepSeek 开放平台](https://platform.deepseek.com/)
2. 注册账号
3. 在 API Keys 页面创建新的 API Key
4. 复制 `sk-` 开头的密钥，填入 `config.json` 的 `llm.api_key` 字段

DeepSeek 新用户注册即送免费额度，`deepseek-chat` 模型价格极低（约 ¥1/百万Token），日常聊天一天花费不到1元。

### Q：启动失败怎么办？

**排查步骤**：

1. **运行健康检查**：`python healthcheck.py`，查看哪些项失败
2. **检查 Python 版本**：`python --version`，需要 3.10+
3. **检查依赖**：`pip install -r requirements.txt` 确保依赖已安装
4. **检查配置文件**：确认 `config.json` 格式正确，`api_key` 已填写
5. **检查 DNA 路径**：确认 `dna_path` 指向的目录下有 `system_prompt.md` 文件
6. **查看错误信息**：启动时的错误提示通常已经说明了问题所在

**常见错误**：

| 错误信息 | 原因与解决方案 |
|----------|----------------|
| `启动失败: config.json not found` | 配置文件不存在，复制 `config.example.json` 为 `config.json` |
| `ModuleNotFoundError: No module named 'requests'` | 依赖未安装，运行 `pip install -r requirements.txt` |
| `DNA加载失败` | `dna_path` 路径不正确，或目录下缺少 `system_prompt.md` |
| `Connection error` / `API连接失败` | API Key 无效或网络不通，检查 Key 和网络 |

### Q：QQ 连不上怎么办？

**NapCat 未连接**：

1. 确认 NapCat 已启动并登录QQ
2. 确认 NapCat WebUI 中 WebSocket Client 已配置：
   - URL: `ws://127.0.0.1:6199/ws`
   - 消息格式: `Array`
   - Token: 留空
3. 确认运行器已启动且端口为 6199
4. 确认没有其他程序占用 6199 端口

**检查端口占用**：

```bash
# Linux
ss -tlnp | grep 6199

# Windows
netstat -ano | findstr 6199
```

**NapCat 频繁断线**：
- 检查网络稳定性
- QQ 可能触发风控，尝试降低消息频率
- 更新 NapCat 到最新版本

### Q：内存和存储占用大吗？

- **内存**：运行器本身约占用 50-100MB 内存。代码沙箱执行时会额外创建子进程（默认限制 256MB）
- **存储**：主要存储为 `memory/` 目录下的JSON文件。日常聊天产生的记忆数据每天约几十KB，长期使用（数月）通常在数十MB以内
- **清理**：`memory/` 目录下的数据可以安全删除（会丢失所有记忆和成长数据），运行器会在下次启动时自动重建

### Q：如何更换AI模型？

修改 `config.json` 中的 `llm` 配置：

```json
{
  "llm": {
    "base_url": "https://api.openai.com/v1",
    "api_key": "sk-你的OpenAI密钥",
    "model": "gpt-4o-mini"
  }
}
```

只要 API 兼容 OpenAI 格式（`/v1/chat/completions` 端点），都可以使用。

### Q：可以在手机上用吗？

运行器需要在电脑上运行（需要 Python 环境）。手机端可通过 QQ 私聊/群聊与机器人对话（需先在电脑上启动 QQ 模式）。

---

## 开源协议

本项目基于 [MIT License](LICENSE) 开源。

你可以自由使用、修改、分发本项目代码，但请保留原始许可证声明。

---

## 相关链接

- **NapCat（QQ框架）**：[NapCatQQ](https://github.com/NapNeko/NapCatQQ)
- **DeepSeek（推荐LLM）**：[platform.deepseek.com](https://platform.deepseek.com/)

---

*知乐人格DNA · 代码级运行器 · 让AI角色在你的电脑上活起来。*
