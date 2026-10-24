# 报名草稿

把仓库发布到参赛者自己的公开 GitHub 账号下，确认参赛声明后按下面格式提交。

Issue 标题：

```text
麦懂你：按用餐习惯推荐餐品组合
```

Issue 正文（把项目地址替换为真实公开地址）：

```text
【参赛申请】
项目名称：麦懂你
项目地址：YOUR_PUBLIC_GITHUB_REPOSITORY_URL
项目简介：固定要两个汉堡、不喝套餐饮料的人，每次点餐都要重算一遍。麦懂你把这句话变成硬约束：按门店实时菜单枚举满足习惯的组合，逐个调用 calculate-price 试算含优惠的应付总价，再按口味与反馈打分，并逐条说明其余组合为什么被排除。
```

每个字段和值保持在同一行，项目地址填写普通 URL。

## 提交前核对

- [ ] 仓库为 public，且创建时间在 2026-01-01 之后
- [ ] 根目录含 `README.md`、`CONTEST_DECLARATION.md`、`MCP_INTEGRATION.md`、`mcp-config.example.json`
- [ ] 参与 WorkBuddy 专项：根目录含 `workbuddy.md`
- [ ] 全仓库搜索无 Token、手机号、地址、账号；`private/` 未提交
- [ ] `python -m unittest discover -s tests` 全部通过
- [ ] README 首屏截图 `docs/terminal.svg` 可正常渲染
- [ ] 仓库 Topics 建议：`mcp` `mcdonalds` `ai-agent` `skill` `python` `recommendation`

提交位置与最新要求见[官方赛事仓库](https://github.com/M-China/mcd-developer-innovation-challenge)。以系统在报名 Issue 中回复成功为准；当前尚未提交。

## 已知风险

本项目**未使用真实 MCP Token 完成生产联调**（见 `MCP_INTEGRATION.md` 第 1 节）。规则要求"参赛项目须真实使用麦当劳 MCP 能力"。MCP 调用链已在代码层完整实现并有测试覆盖，但没有真实账号的调用记录。若评审以此为核验点，存在被判不符合要求的风险；补齐方式见 `MCP_INTEGRATION.md` 第 6 节。
