# 参赛报名提交草稿

确认仓库已发布至参赛者公开 GitHub 账号下，并核对 [CONTEST_DECLARATION.md](CONTEST_DECLARATION.md) 后，前往官方赛事仓库提交 Issue。

## Issue 标题

```text
麦懂你：按用餐习惯推荐餐品组合
```

## Issue 正文（替换项目地址为真实仓库 URL）

```text
【参赛申请】
项目名称：麦懂你（mai-habit）
项目地址：https://github.com/pha1aris/mai-habit
项目简介：固定吃两个汉堡、套餐饮料从不喝、单餐预算 28 元——这些不该是被动推测的“猜你喜欢”，而是硬性约束。麦懂你将用户的固定用餐习惯作为核心过滤规则：调用 query-meals 获取门店实时菜单，按习惯枚举合规组合（支持同品多份、类别上下限剪枝），对每个候选组合单独调用 calculate-price 精准试算券后应付总价；基于有效证据动态归一化权重打分，输出三档透明推荐，并逐条公开未入选组合的具体排除原因。安全合规：客户端白名单仅放行 8 个只读查询与试算工具，在代码层坚决拦截 create-order、cancel-order 等任何写操作。工程亮点：不隐式猜测 API 结构，采用显式 mapping 配置并强校验金额单位；坚决拒绝以菜单标价机械相加冒充实付总价。附带脱敏回放样本，零依赖无 Token 亦可端到端跑通完整链路；在线试玩：https://pha1aris.github.io/mai-habit/
```

> **注意事项**：每个字段与取值请保持在同一行，项目地址使用普通纯文本 URL，标题与正文之间避免多余空行。

## 提交前清单核对

- [ ] 仓库设为 Public 公开，且创建时间在 2026-01-01 之后
- [ ] 根目录完备包含 `README.md`、`CONTEST_DECLARATION.md`、`MCP_INTEGRATION.md`、`mcp-config.example.json`
- [ ] 参与 WorkBuddy 专项：根目录包含 `workbuddy.md`
- [ ] 全仓库检索确认无明文 Token、手机号、真实地址等敏感隐私信息；`private/`、`.workbuddy/` 均已被 `.gitignore` 排除
- [ ] 本地运行 `python -m unittest discover -s tests` 全部通过（共 87 项测试）
- [ ] GitHub Actions CI 流水线状态全绿（覆盖 Python 3.10–3.13、端到端冒烟验证、SVG 截图保真校验与演示页枚举一致性）
- [ ] README 首屏终端渲染图 `docs/terminal.svg` 显示正常
- [ ] 仓库推荐配置 Topics：`mcp` `mcdonalds` `mcd-mcp` `ai-agent` `workbuddy` `skill` `python` `recommendation` `meal-planner`

提交入口及最新评审指引参见[官方赛事仓库](https://github.com/M-China/mcd-developer-innovation-challenge)。以官方系统在报名 Issue 中的正式回复为准。

## 已知风险与合规说明

本项目在开发阶段**尚未绑定真实生产 Token 完成全量生产环境联调**（详见 `MCP_INTEGRATION.md` 第 1 节）。赛事规则要求“参赛项目须真实使用麦当劳 MCP 能力”。虽然本项目的 MCP 通信链、协议解析、参数校验及只读安全策略已在代码层完整实现并通过严密测试，但尚未产生真实生产账号的在线调用凭证。若评审侧以此为硬性核验指标，可能存在资质审核风险；相关真实环境接入与凭证补齐步骤详见 `MCP_INTEGRATION.md` 第 6 节。
