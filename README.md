# VendFill 售货机补货

按货道容量、库存与在途量计算缺口，生成不超缺口、非负的补货单。

技术栈：Python 3.12 / FastAPI / SQLAlchemy / PostgreSQL / Vue 3 / TypeScript / Vite

## 启动

```bash
docker compose up --build
```

| 服务 | 地址 |
| --- | --- |
| 前端 | http://localhost:4800 |
| API | http://localhost:9800 |
| API 文档 | http://localhost:9800/docs |
| Postgres | localhost:5449 |

健康检查：`GET http://localhost:9800/api/health`

## 使用说明

1. 在「点位」「货道」查看售货机布局与库存。
2. 在「销量」了解近期出货。
3. 打开「补货单」按缺口生成建议补货量。
4. 在「满仓」「汇总」查看已满货道与补货合计。
5. 打开「只读巡检」按当前库存核对：待补件数、满仓道数、超占道数，与当场生成的补货单对同一套数。巡检全程只读，不生成也不改写补货单（不会走无单时自动落单的「最近单」入口）。

## 只读巡检与退出码

接口：`GET /api/refills/inspection?location_id=1`，每次都从数据库现读货道、
走与生成补货单完全相同的口径（gap = 容量 − 库存 − 在途），改了库存再巡检立即吃新数，不依赖任何进程内旧计数。

命令行对账（只读取数、独立复算）：

```bash
docker compose exec api python inspect_cli.py 1
```

| 退出码 | 含义 |
| --- | --- |
| 0 | 对账成功：巡检数与按当前库存独立复算一致 |
| 2 | 点位不存在 |
| 3 | 点位存在，但超占道被算进了满仓侧（与 2 不混用） |
| 1 | 其他对账失败 |

口径约定：库存＋在途＞容量为**超占**（如种子数据的口香糖 C2：24 库存＋2 在途＞24 容量），
只计入超占道数，绝不计入满仓；库存＋在途＝容量才是满仓。

## 开发与测试

```bash
docker compose exec api pytest -q
```
