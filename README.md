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
5. 在「只读巡检」按当前库存对账：待补件数、满仓道数、超占道数，与当场补货单同一套数；巡检全程只读，不生成、不改写补货单。

## 只读巡检

- HTTP：`GET http://localhost:9800/api/inspection?location_id=1`
- CLI（容器内）：`python -m app.inspect [location_id]`

CLI 退出码：`0` 对账成功；`2` 点位不存在；`3` 超占道被算进满仓数（2 与 3 互斥）。
巡检直接重查货道表，库存改动后立即吃新值；超占道（库存＋在途＞容量）单列，不计入满仓。

## 开发与测试

```bash
docker compose exec api pytest -q
```
