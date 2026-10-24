# 麦当劳 MCP 集成说明

## 1. 状态与证据

服务地址：`https://mcp.mcd.cn`，采用 Streamable HTTP，`Authorization: Bearer` 的值来自本机环境变量 `MCD_MCP_TOKEN`。

客户端已实现：初始化握手、`notifications/initialized` 通知、`Mcp-Session-Id` 会话延续、`MCP-Protocol-Version` 协商、JSON 与 SSE 双响应解析、工具分页发现、按实时 `inputSchema` 校验必填参数、只读工具白名单。

**已完成的验证：** 上述客户端逻辑由单元测试覆盖（模拟收发、SSE 事件流、分页游标、协议错误、HTTP 401 不回显 Token）；从菜单响应到候选枚举、逐个计价、排序的完整链路可用仓库内回放样本端到端跑通（`tests/test_pipeline.py`）。

**尚未完成的验证：** 没有使用真实 MCP Token 完成生产环境联调。仓库内 `examples/replay/` 是虚构样本，其中的门店编号、商品编码与价格都不是麦当劳真实数据。因此本项目**不能**被引用为"已完成真实 MCP 计价验证"。

本文把"已实现的调用路径"和"尚待真实环境确认的事实"分开陈述，不把计划调用写成已发生调用。

官方依据：[MCP 服务指南](https://github.com/M-China/mcd-mcp-server)、[参赛规则](https://github.com/M-China/mcd-developer-innovation-challenge/blob/main/activityGuidelines.md)。具体工具参数以 `tools/list` 返回的实时 `inputSchema` 为准。

## 2. 使用的工具与调用条件

| 工具 | 本项目用途 | 调用条件 |
| --- | --- | --- |
| `now-time-info` | 确认当前日期与服务端时间 | 开始一次真实推荐时 |
| `query-nearby-stores` | 查询用户给出位置附近门店 | 尚未确定门店时 |
| `query-meals` | 获取门店当前菜单与可售状态 | 每次真实推荐，结果作为候选池 |
| `query-meal-detail` | 展开套餐组成与可替换项 | 套餐组成不明确时 |
| `query-store-coupons` / `query-my-coupons` | 确认可用券与使用条件 | 用户需要使用账户券时 |
| `calculate-price` | 对每个候选组合试算应付总价 | 每个枚举出的候选 |
| `list-nutrition-foods` | 营养信息 | 用户明确询问时；当前排序未使用 |

客户端**不调用**任何写操作工具。`create-order`、`cancel-order`、`auto-bind-coupons`、`draw-lottery`、`mall-create-order` 等即使服务端返回，也会被 `READ_TOOLS` 白名单拦截。

## 3. 业务调用路径

命令层面，一次完整的 `plan` 流程是：

```text
query-meals 原始响应
   └─ adapter.meals()         按 mapping 映射为规范化菜单（编码/名称/类别/标价/标签/餐段）
        └─ planner.build()    按 category_limits 枚举合法组合（同款多份、类别上下限）
             └─ calculate-price × N   每个组合单独试算，取应付总价
                  └─ adapter.quote()  规范化报价（金额、时间、门店、餐段）
                       └─ recommender.rank()  过滤 → 归一化权重打分 → 三档推荐 + 排除原因
```

对应命令：

```bash
# 实时（需要 Token）
python habit.py mcp-tools                       # 查看真实工具与 inputSchema
python habit.py plan --profile private/profile.json \
  --menu private/menu-response.json --mapping private/mapping.json \
  --meal lunch --budget 30 --store <门店编号>

# 回放（无需 Token，验证链路完整性）
python habit.py plan --profile examples/profile.demo.json \
  --menu examples/replay/menu.json --prices examples/replay/prices.json \
  --mapping examples/replay/mapping.json \
  --meal lunch --budget 28 --store MCD-DEMO-001
```

`plan` 与 `demo` 的区别：`demo` 读的是内置的静态候选文件，只验证排序；`plan` 走的是"原始响应 → 映射 → 枚举 → 计价 → 排序"的完整链路，与实时模式的差别仅在于报价来自本地回放文件。

## 4. 字段映射为什么是显式的

麦当劳 MCP 的响应字段名可能随版本变化。本项目**不硬编码、不猜测字段名**，而是要求一份 mapping 文件显式声明路径：

```json
{
  "menu": {
    "list": "categories.*.items.*",
    "price_unit": "yuan",
    "fields": {
      "code": "productCode", "name": "productName",
      "category": "categoryName", "price": "price",
      "tags": "tasteTags", "available": "saleStatus",
      "meal_times": "mealPeriods"
    }
  },
  "price_request": {
    "storeCode": "${store_id}",
    "mealPeriod": "${meal}",
    "items": "${items}",
    "itemTemplate": {"productCode": "${code}", "quantity": "${quantity}"}
  },
  "quote": {"total_cents": "payPrice", "price_unit": "yuan", "valid_until": "expireTime"}
}
```

规则：

- 点路径寻址，`*` 展开数组（`categories.*.items.*` 会拍平为一维列表）。
- `price_unit` 必须声明是 `yuan` 还是 `cents`。金额单位歧义会被拒绝，不做"看起来像分就当分"的猜测。
- `${...}` 是计价请求模板占位符。整段占位符（如 `"${items}"`）保留原始 JSON 类型，嵌入字符串（如 `"x-${meal}"`）会转成文本。
- 中文类目名（汉堡 / 饮料 / 小食 / 套餐 / 甜品）会归一到 `burger / drink / side / combo / dessert`，可用 mapping 里的 `categories` 覆盖。
- 映射失败直接报错（缺少必需字段、路径定位不到数组、模板变量不存在），**不会**静默产出空候选或错误价格。

示例映射见 `examples/replay/mapping.json`。它是虚构样本的映射，**不是官方字段定义**，接真实服务时必须按自己看到的响应重写。

## 5. 候选数据契约

规范化文件包含 `mode`（`demo` / `live`）、`store_id`、`candidates`。每个候选：

- `id`、`name`、`items`：组成。每个 item 含 `name`、`category`、正整数 `quantity`；同款两份写成一条 `quantity=2`。
- `tags`、`tags_confirmed`：口味标签及确认标识。组合标签取各餐品标签的并集；无标签数据源时 `tags_source` 记为 `none`，推荐会退化为按价格排序，而不是编造标签。
- `categories_confirmed`：已展开并核实全部套餐组成（含搭售饮料）。
- `checked_avoid_tags`：已核实的忌口检查范围。
- `available`、`meal_times`：真实可售状态与适用餐段。
- `quote.source`：实时为 `calculate-price`，回放为 `demo`。
- `quote.store_id` / `quote.meal_time`：计价上下文，必须与本次门店和餐段一致。
- `quote.total_cents`：**应付总价**（整数分），不是标价相加。
- `quote.quoted_at`：带时区的实际调用时间，推荐时手动超过 15 分钟即判失效。
- `quote.valid_until`：可选，取券或报价已知失效时间的最早值。

`mode=live` 只触发本地一致性校验，不构成来源认证；真实性只能由实际联调证明。

## 6. 真实联调需要完成的事

1. 用有效 Token 完成 `initialize` 与 `tools/list`，核对本文工具表与线上是否一致。
2. 选定真实门店与餐段，`query-meals` 取菜单，`query-meal-detail` 展开套餐组成。
3. 按真实响应重写 mapping，用 `plan` 至少试算两种"双汉堡、不含饮料"的候选。
4. 与官方点餐页面逐项核对：件数、券条件、应付金额。
5. 保存脱敏证据（隐去 Token、地址、账号、券信息），删除 `private/` 下的原始响应后再发布。

在上述 1–4 完成之前，本项目只能声称"链路已实现并可回放验证"，不能声称"真实计价已验证"。
