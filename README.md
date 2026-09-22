# 冰川洞穴染料示踪 · 全局最小汇流树

用户通过真实 HTTP API 提交 2–40 个唯一 ASCII 采样点、一个注入根和至多 160 条带
**唯一标识**与**非负整数代价**的**有向**通道（允许平行通道、禁止自环）。后端用
**从零实现**的 Chu–Liu/Edmonds 算法（不调用任何现成图优化库）精确求出：

- 每个非根点**恰有一条**入选通道；
- 全部点从根可达（根的入边永远不会入选）；
- 总代价全局最小；
- 在所有同优树中，取**升序通道标识序列字典序最小**的规范树；
- 并给出每一次有向环收缩、选入通道与展开替换的可复算记录；
- 无解（存在不可达点）或输入非法时，返回**不可达点列表**与**明确原因**。

前端用网络图与收缩记录联动展示规范树、逐边代价和证据；提交失败后输入原样保留。

## 目录结构

```
backend/        FastAPI 后端（自研 CLE 算法 + 校验 + 单元/HTTP 测试）
  app/arboreal.py   Chu–Liu/Edmonds 与字典序扰动（无第三方图库）
  app/models.py     输入校验（2..40 点、唯一 id、自环/代价等）
  app/main.py       /health、/api/v1/info、/api/v1/solve
  tests/            85 个单元 + HTTP 测试（含 60 组随机图暴力枚举交叉验证）
web/            React 18 + Vite + TypeScript（手写 SVG 网络图，无图库）
verify/         一次性校验服务（单测、前后端构建、API/HTTP 冒烟、样例核对）
docker-compose.yml
```

## 字典序破同价是如何精确实现的

设通道数为 `m`，按通道标识 ASCII 码点升序给出内部名次 `cid = 1..m`
（名次 1 = 最小标识），令 `SCALE = 2^m`，通道扰动权重

```
w(e) = cost(e)·SCALE − 2^(m − cid(e))
```

算法最小化权重之和：

- 位部分绝对值恒小于 `SCALE`，因此真实代价小的树永远优先；
- 同价时等价于最大化一个二进制向量：某位为 1 当且仅当对应通道入选。
  最高位对应最小 id，逐位比较恰好就是“升序 id 序列”的字典序比较。

CLE 的折减权重由扰动权重做普通减法得到（可能为负，属正常），
因此该次序在任意层收缩后仍保持。响应的 `evidence.perturbation` 给出
`scale / perturbed_total / selected_bit_vector` 等，可独立复算。

## API

`POST /api/v1/solve`

```json
{
  "points": ["R", "a", "b"],
  "root": "R",
  "channels": [
    {"id": "e1", "source": "R", "target": "a", "cost": 4},
    {"id": "e2", "source": "a", "target": "b", "cost": 1}
  ]
}
```

成功 `200`：`tree.edges`（逐边源/目标/代价）、`tree.total_cost`、
`evidence.rounds`（每层选入、有向环、收缩）与 `evidence.expansions`
（移除环上通道 ⇒ 换入外部通道）。

无解 `422`：`error.message` 给出原因，`unreachable` 列出全部不可达点。
输入错误 `400`：`error` 含 `code/message/field`。通道 id 接受字符串或
JSON 整数（整数按字符串码点序参与字典序，例如 `"10" < "2"`）。

## 用 Docker Compose 运行

端口可通过宿主环境变量配置（容器内部固定 api=8000、web=8080）：

```bash
# 可选：自定义宿主端口
export API_PORT=8000 WEB_PORT=8080

docker compose build
docker compose up -d            # 访问 http://localhost:${WEB_PORT:-8080}
```

健康检查：

- api 容器：`GET :8000/health`（Docker HEALTHCHECK + compose healthcheck）；
- web 容器：`GET :8080/`（nginx 内置 HEALTHCHECK）。
  浏览器同源访问 `/api/*` 与 `/health` 由 nginx 反代到 api。

### 一次性 verify 服务

`verify` 是 `restart: "no"` 的一次性服务（compose profile `verify`）。
它对**真实运行中的 api 与 web 容器**执行：

1. 后端单元测试（pytest，含暴力枚举交叉验证）；
2. 后端字节码构建 + 前端生产构建（`tsc -b && vite build`）；
3. API / HTTP 冒烟（api `/health`、web `/`、同源反代 `/health`、真实求解）；
4. 四类样例核对：**嵌套环、平行通道、同优规范树、不可达点**——
   每类都用独立的暴力枚举重算最优树与字典序解，再与线上 API 返回值比对，
   同时检查页面构建产物内嵌的是同一批样例。

随后退出，**退出码即结论**：

```bash
docker compose build
docker compose up --abort-on-container-exit --exit-code-from verify verify
echo "verify exit code: $?"   # 0 = 全部通过
```

## 本地开发（不用 Docker）

```bash
# 后端
cd backend
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000

# 前端
cd web
npm install
npm run dev        # http://localhost:5173 ，/api 代理到 http://localhost:8000
```
