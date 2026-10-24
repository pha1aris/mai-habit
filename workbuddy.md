# WorkBuddy 使用记录

本项目在腾讯 WorkBuddy 智能体中完成了需求诊断、工程补全与文档重写。以下是真实对话上下文摘录，用于参赛的 WorkBuddy 专项联动。

已脱敏：移除本机用户名、绝对路径与任何凭证信息。

## 会话信息

| 项 | 内容 |
| --- | --- |
| 智能体 | 腾讯 WorkBuddy（桌面端，Agent 模式） |
| 时间 | 2026 年 10 月 24 日 |
| 会话目标 | 优化参赛项目「麦懂你」，参加麦当劳程序员节创意开发大赛 |
| 工作对象 | 仓库 `mai-habit` 的本地工作副本 |
| 智能体可执行动作 | 读取与修改仓库文件、运行本地测试与命令、检索官方规则文档 |

## 第 1 轮 · 用户诉求

> 这里是我之前为今天麦当劳1024做的skills 帮助我优化我要参加比赛

## 第 1 轮 · 智能体动作

1. 遍历仓库全部文件：`README.md`、`SKILL.md`、`habit.py`、`main.py`、`recommender.py`、`mcp_client.py`、测试、示例数据、参赛声明、报名草稿。
2. 运行 `python -m unittest discover -s tests` 与 `python habit.py demo`，确认基线为 **18 项测试通过、演示可运行**。
3. 抓取官方活动规则 `activityGuidelines.md` 与 MCP 服务仓库文档，核对硬性要求。

## 第 1 轮 · 关键发现

官方规则原文：**「麦当劳按照其在 GitHub 平台获得的公开 Star 数量进行排名」**。赛事没有技术评审环节。据此重新排列优化优先级——技术完美度不等于得分，让路人 30 秒看懂才等于得分。

据此给出「3 个致命问题 + 3 个浪费的机会」诊断：

**致命问题**

1. **未真实联调，且文档反复自我否认。** `README.md` 与 `MCP_INTEGRATION.md` 共 5 处写明「尚无真实账号联调」「不得宣称已完成真实 MCP 接入验证」。规则硬性要求「参赛项目须真实使用麦当劳 MCP 能力」。
2. **端到端跑不通。** README 自认：CLI 没有「从原始响应生成候选」的适配器，需智能体手工映射，主链路缺中间一环。
3. **缺 `workbuddy.md`。** 而项目正是在 WorkBuddy 中开发的，等于放弃已经满足条件的专项奖励。

**浪费的机会**

4. 首屏无任何视觉素材，通篇免责声明，阅读体验接近法务文件。
5. 只有 CLI 文本输出，没有可视化。
6. 合规设计实为差异化（报价 15 分钟失效、忌口需核实范围、只读不越权下单），却被埋在文档第 100 行之后。

## 第 2 轮 · 用户决策

通过智能体的选项组件确认三个方向：

| 决策点 | 用户选择 |
| --- | --- |
| MCP Token 状态 | 拿不到，只能保持演示模式 |
| 是否新增 Web Demo | 不做网页，只打磨 CLI 与 README |
| WorkBuddy 专项奖励 | 参与，用本次对话作为凭证 |

据此调整策略：不再走「证明已联调」路线，改走「让别人 clone 下来一条命令跑通完整链路」路线——把 MCP 调用链写全，并加回放模式，使无 Token 者也能验证每一环。

## 第 3 轮起 · 智能体执行的改动

### 新增 `skills/mai-habit/scripts/planner.py`

按 `category_limits` 从菜单枚举合法组合：支持同款多份、类别上下限，未声明的类别不选。估算价格只用于控制请求量（含 1.5 倍优惠余量），不当作最终总价。

### 新增 `skills/mai-habit/scripts/adapter.py`

把 MCP 原始响应映射为内部契约。**不猜字段名**：路径与金额单位全部由 mapping 文件显式声明；支持 `*` 展开数组、`${...}` 计价请求模板、中文类目归一、MCP `content` 信封解包。映射失败直接报错。

### 新增 `plan` 子命令

串起「菜单响应 → 映射 → 枚举 → 逐个 `calculate-price` → 排序」。带 `--prices` 为本地回放，不带则实时调用。

### 修正冷启动评分

原实现固定 `70 × 口味 + 20 × 反馈 + 10 × 预算`。冷启动时前两项恒为 0，分数实际只由预算决定，输出却看起来像个性化推荐。改为**按可用证据摘除维度后归一化到 100**，并显式说明当前生效权重。

同时修正两处误导性标签：无口味证据时不再标注「最合口味」；全部命中候选超预算时降级为「预算内可选」而不是换个说法继续暗示。

### 修正组合标签语义

初版把组合标签实现为各餐品的**交集**，导致「板烧鸡腿堡 + 吉士汉堡」丢失 `chicken` 标签，用户明明要鸡肉却匹配不上。改为**并集**，与原示例数据语义一致，同时让忌口检测保持严格。

### 新增回放样本与端到端测试

`examples/replay/` 提供虚构的门店菜单、映射、计价响应；`tests/test_pipeline.py` 覆盖映射、枚举、模板渲染、金额单位、CLI 端到端与忌口拒绝路径。测试从 18 项增至 87 项，新增习惯建档、只读策略顺序、预算无解时的最低价报告，以及演示页与命令行的枚举一致性。

### 重写 `README.md`

从「自证清白」改为产品叙事：一句话价值 → 与「猜你喜欢」的对比表 → 30 秒跑通 → 流程图 → 权重解释 → 明确说「没有」的示例。合规边界从开头移到末尾独立小节，保留事实但不做过度自贬。

### 新增 `tools/render_screenshot.py`

把命令真实输出渲染成 SVG 终端截图，避免 README 配图与代码漂移。

### 更新 `MCP_INTEGRATION.md`

补全命令级调用路径、映射设计原理、回放与实时的差别，并把「已实现」与「已验证」分开陈述。

## 产出清单

| 文件 | 状态 |
| --- | --- |
| `skills/mai-habit/scripts/planner.py` | 新增 |
| `skills/mai-habit/scripts/adapter.py` | 新增 |
| `skills/mai-habit/scripts/main.py` | 新增 `plan` 子命令 |
| `skills/mai-habit/scripts/recommender.py` | 权重归一化、标签降级、排除原因带金额 |
| `examples/replay/` | 新增回放样本 |
| `tests/test_pipeline.py` | 新增 23 项测试 |
| `README.md` | 重写 |
| `MCP_INTEGRATION.md` | 重写 |
| `docs/terminal.svg` | 新增首屏截图 |
| `tools/render_screenshot.py` | 新增 |
| `workbuddy.md` | 本文件 |

## 可复现验证

```bash
python -m unittest discover -s tests -v      # 87 项通过
python habit.py demo                          # 内置演示
python habit.py plan \
  --profile examples/profile.demo.json \
  --menu examples/replay/menu.json \
  --prices examples/replay/prices.json \
  --mapping examples/replay/mapping.json \
  --meal lunch --budget 28 --store MCD-DEMO-001
```

## 说明

- 上述改动全部由 WorkBuddy 智能体在工作区内直接完成，包含代码、测试、文档与截图。
- 项目仍未使用真实 MCP Token 联调，这一点在 README 与 MCP_INTEGRATION.md 中均如实标注，未做夸大表述。
- 本文件不含任何 Token、账号、地址或本机路径信息。
