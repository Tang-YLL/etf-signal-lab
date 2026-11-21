# 端到端测试

端到端测试通过 Playwright 启动真实浏览器、Vite 前端和 FastAPI 后端，使用 SQLite 和真实刷新线程验证用户可观察行为。测试服务只替换外部行情接口为确定性夹具，不会请求东方财富、腾讯或其他上游行情源，也不会修改 NAS 数据。

## 本地运行

```bash
cd frontend
npm ci
npx playwright install chromium
npm test -- --run
npm run e2e
```

如果 Python 虚拟环境不在默认位置，可以指定后端解释器：

```bash
E2E_PYTHON=/绝对路径/bin/python npm run e2e
```

`npm test` 运行 Vitest 单元/组件测试；`npm run e2e` 运行 Playwright 浏览器验收。E2E 会启动两个本地服务：`127.0.0.1:8000` 的确定性 FastAPI 服务和 `127.0.0.1:5173` 的 Vite 开发服务。测试结束后，临时数据库位于 `frontend/.e2e-data/`，报告和失败附件位于 `frontend/playwright-report/`、`frontend/test-results/`，这些目录均已加入 `.gitignore`。

## 覆盖范围

- 免登录进入工作台、打开/关闭添加 ETF 弹窗、粘贴/Enter/Escape、遮罩关闭和焦点恢复。
- 搜索 `159307`，检查基金简称、基金全称、场内简称，并完成添加、刷新、详情页、K 线、RSI、MA20、BOLL、PENDING 和次日观察价 API 验收。
- 搜索并添加 `510300`、`159915`，检查 OHLCV 合法性和刷新后持久化。
- 策略规则页、数据与系统页、行情提供者状态以及手机视口无横向溢出。
- 搜索接口返回 502 时，弹窗保持可用并展示可见错误。

测试夹具会将最新一根 K 线标记为 `PENDING`，此前日期标记为 `CONFIRMED`，因此可以在不等待十分钟重复采样的情况下同时验收待确认状态和已确认阈值快照。
