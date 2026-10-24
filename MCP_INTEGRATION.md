# 麦当劳 MCP 集成规范与实现说明

## 1. 协议状态与验证边界

- **服务接入点**：`https://mcp.mcd.cn`
- **传输层协议**：Streamable HTTP（支持标准 JSON 与 Server-Sent Events / SSE 流式响应）
- **鉴权机制**：`Authorization: Bearer <token>`，凭据安全注入自本地环境变量 `MCD_MCP_TOKEN`

客户端在工程层已完备实现：初始化握手协议、`notifications/initialized` 状态通知、`Mcp-Session-Id` 会话延续、`MCP-Protocol-Version` 协议版本协商、JSON 与 SSE 混合双响应流解析、工具列表游标分页拉取、基于服务端实时 `inputSchema` 强校验参数、只读安全白名单防御拦截。

**已通过的验证**：
- 上述客户端网络通信与协议解析逻辑已获完整单元测试覆盖（包含模拟网络收发、SSE 事件流拆包、分页游标遍历、协议异常捕获、HTTP 401 凭据绝不泄露等防御机制）；
- 从菜单响应到候选枚举、逐一计价、排序打分的完整业务链路，均可通过仓库内脱敏回放样本端到端自动化跑通（见 `tests/test_pipeline.py`）。

**尚待生产环境确认的事项**：
- 本项目在开发阶段**尚未绑定真实生产 Token 完成生产环境在线联调**。仓库内 `examples/replay/` 均为脱敏虚构样本，其中门店编号、餐品编码及标价均非麦当劳线上真实数据。因此本项目**不宣称**已完成麦当劳线上真实计价联调。

> **工程原则**：本文恪守客观真实的工程原则，将「已在代码层完整实现的协议调用路径」与「尚待生产环境联调确认的数据事实」清晰分立陈述，杜绝将预期设计虚构成已发生事实。

官方技术参考：[麦当劳 MCP 服务指南](https://github.com/M-China/mcd-mcp-server)、[大赛参赛指南](https://github.com/M-China/mcd-developer-innovation-challenge/blob/main/activityGuidelines.md)。具体工具元数据以 `tools/list` 实时下发的 `inputSchema` 为准。

## 2. 调用的工具能力与触发策略

| 工具名称 | 本项目核心用途 | 调用触发时机 |
| --- | --- | --- |
| `now-time-info` | 校验当前服务器时间与餐段周期 | 发起实时推荐流程初始阶段 |
| `query-nearby-stores` | 基于地理坐标检索附近门店 | 用户尚未明确指定就餐门店时 |
| `query-meals` | 获取目标门店当前餐段菜单与在售状态 | 发起推荐的主入口，构建初始候选池 |
| `query-meal-detail` | 展开套餐构成与可替换餐品明细 | 套餐组成不透明或需核对搭售饮品时 |
| `query-store-coupons` / `query-my-coupons` | 查询门店可用优惠券与个人卡券详情 | 用户明确需要核销账户券时 |
| `calculate-price` | 精准试算指定候选组合的券后应付总价 | 针对枚举出的每个合规候选组合 |
| `list-nutrition-foods` | 查询餐品热量与营养指标 | 用户主动询问时按需调用（默认打分不依赖） |

**安全拦截边界**：客户端**坚决杜绝调用任何写操作工具**。即便服务端元数据包含 `create-order`、`cancel-order`、`auto-bind-coupons`、`draw-lottery`、`mall-create-order` 等接口，也会在客户端底层的 `READ_TOOLS` 白名单机制中被无条件硬性拦截。

## 3. 核心业务调用链路

在命令行层面，一次完整的 `plan` 决策流程如下：

```text
query-meals 原始响应
   └─ adapter.meals()         依据 mapping 映射为规范化菜单（编码/品名/类别/标价/口味标签/餐段）
        └─ planner.build()    依据 category_limits 枚举合规组合（同品多份、类别上下限剪枝）
             └─ calculate-price × N   对每个合法组合发起独立计价，获取真实券后实付总价
                  └─ adapter.quote()  规范化报价对象（实付金额、有效时限、门店上下文、餐段）
                       └─ recommender.rank()  规则过滤 → 动态归一化权重打分 → 输出三档推荐与排除清单
```

执行命令示例：

```bash
# 实时在线模式（需要有效 MCP Token）
python habit.py mcp-tools                       # 查看服务端开放的工具与 inputSchema
python habit.py plan --profile private/profile.json \
  --menu private/menu-response.json --mapping private/mapping.json \
  --meal lunch --budget 30 --store <门店编号>

# 脱敏回放模式（零依赖、无需 Token，用于验证完整链路逻辑）
python habit.py plan --profile examples/profile.demo.json \
  --menu examples/replay/menu.json --prices examples/replay/prices.json \
  --mapping examples/replay/mapping.json \
  --meal lunch --budget 28 --store MCD-DEMO-001
```

> **`plan` 与 `demo` 的本质区别**：`demo` 仅读取静态预制候选集，用于展示排序交互；而 `plan` 则完整走通“原始响应 → 动态映射 → 组合枚举 → 精准试算 → 综合排序”的端到端大流水线。回放模式与实时模式唯一的差异仅在于将下游网络报价替换为本地样本文件。

## 4. 声明式字段映射的设计考量

麦当劳 MCP 开放平台的响应字段结构可能随服务版本迭代发生变化。与其在代码中硬编码脆弱的推测字段，并在格式变动时悄然产生不可预知的计算偏差，本项目选择将数据映射完全显式外置于 mapping 配置文件中，严格遵循“不匹配即刻报错”原则：

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

**解析与映射规则**：
- **点路径寻址**：支持通过 `*` 通配符展开多层嵌套数组（例如 `categories.*.items.*` 自动拍平为一维餐品清单）。
- **金额单位严正声明**：`price_unit` 必须显式注明 `yuan`（元）或 `cents`（分）。严格拒绝金额单位歧义，杜绝“按数值大小盲猜单位”的高危行为。
- **请求模板引擎**：`${...}` 占位符支持参数渲染。独立占位符（如 `"${items}"`）保留原生 JSON 数据结构（数组/对象），内嵌占位符则转义为字符串。
- **类目中枢归一化**：中文类目（汉堡 / 饮料 / 小食 / 套餐 / 甜品）自动标准化映射为系统内部枚举 `burger / drink / side / combo / dessert`，亦支持在 mapping 文件的 `categories` 节点自定义别名覆盖。
- **强类型异常快速失败**：若接口缺少必要字段、目标路径无法定位数组、或模板参数缺失，适配器将立即抛出详尽异常，坚决不静默输出虚假候选或错误总价。

> 示例映射文件参见 `examples/replay/mapping.json`。该文件基于脱敏虚构样本构建，并非麦当劳官方字段规范；接入真实线上服务时须依据实际返回的 JSON 数据结构编写映射。

## 5. 候选数据内部契约

适配层输出的规范化候选对象包含 `mode`（`demo` / `live`）、`store_id` 以及 `candidates`。每个候选组合满足以下规范：

- `id`、`name`、`items`：组合明细。每个 item 包含 `name`、`category` 以及正整数 `quantity`；同款 2 份餐品规整为单条记录且 `quantity=2`。
- `tags`、`tags_confirmed`：口味偏好标签并集及确认状态。组合标签为各单品标签的并集；当数据源缺少标签时 `tags_source` 标为 `none`，系统自动降级为纯价格排序，坚决不胡乱编造标签。
- `categories_confirmed`：已递归展开并核验所有套餐构件（重点核验是否含搭售饮料）。
- `checked_avoid_tags`：已由用户显式核验的忌口原料排查清单。
- `available`、`meal_times`：餐品真实在售状态与适用就餐时段。
- `quote.source`：报价来源（实时为 `calculate-price`，脱敏模式为 `demo`）。
- `quote.store_id` / `quote.meal_time`：计价上下文标识，必须与当前门店及餐段严格一致。
- `quote.total_cents`：**券后应付总价**（整数分计），严禁以标价累加充数。
- `quote.quoted_at`：带时区信息的计价时间戳，超过 15 分钟强制判定为报价过期失效。
- `quote.valid_until`：可选，取卡券到期时间与服务端报价有效期的最小值。

## 6. 生产环境联调落地指引

面向具备有效 MCP Token 的开发者，完成线上全链路联调的标准路径：

1. 使用真实 Token 运行 `initialize` 与 `tools/list`，核对线上实际开放的工具列表与本文档记录是否一致；
2. 选取真实就餐门店与餐段，调用 `query-meals` 获取当前菜单，针对组合餐品调用 `query-meal-detail` 核验详细组成；
3. 依据真实响应编写生产 `mapping.json`，运行 `plan` 至少完成两种“双汉堡、不含饮料”典型组合的实付试算；
4. 将试算结果与麦当劳官方小程序/App 购物车结算页进行比对，核实商品件数、优惠抵扣与实付总金额；
5. 脱敏保存调用日志证据（严禁泄露 Token、个人手机号、收货地址与卡券凭证），彻底清理本地 `private/` 临时文件后再行公开发布。
