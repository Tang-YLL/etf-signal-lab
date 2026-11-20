# ETF Signal Lab

个人局域网使用的沪深 ETF 收盘技术观察工具：历史日 K 线、RSI14、MA20、BOLL20、六类候选策略、B1–B3/S1–S3、次日**假设收盘价**条件区间、SQLite 缓存。前端采用 React + TypeScript + ECharts，后端为 FastAPI + SQLAlchemy + Alembic + AKShare，Nginx 统一访问入口。

> **使用边界**：策略参数是未经回测验证的候选默认值，非盈利预测。条件观察价是假设下一交易日以该价格收盘时指标满足条件的档位，**不是预测的市场价格**。只计算指定价格范围内的报价档位；复权、除息和折算会导致理论观察价失真。行情源可能延迟、中断或修订；无供应商最终标志，重复采样确认仍需独立验证。

## 快速部署（Docker）

```bash
git clone https://github.com/Tang-YLL/etf-signal-lab.git
cd etf-signal-lab
cp .env.example .env
docker compose up -d --build
docker compose logs backend   # 首次启动复制随机生成的 admin 密码
```

局域网内浏览器访问：`http://服务器局域网IP:8080`。默认用户名 `admin`，**密码仅在首次启动日志中显示一次**；忘记密码可通过宿主机执行 `docker compose exec backend python -m app.reset_admin` 重置。登录后在「数据与系统」修改密码。

> Docker Compose 使用命名卷 `etf_data` 保存数据库与签名密钥。`docker compose down` 不会删除数据，**`docker compose down -v` 会删除数据卷**，请勿误用。前端为静态页面，后端不向宿主机映射端口。Docker 守护进程应只绑定受信任的局域网接口或经主机防火墙隔离；请勿设置公网转发。

## 操作流程

1. 使用管理员密码登录。
2. 点击「添加 ETF」，按代码/名称搜索，确认身份后选择六类策略之一，**无法核实跟踪标的时应保持「未分类」**，此时仅计算指标、不生成方向性信号。若行情搜索服务不可用，可手动添加准确的 ETF 名称及六位代码。
3. 后端在后台请求 AKShare 的 `fund_etf_hist_em` **未复权日线**，存入 SQLite；行情不足 20 根时指标不可用。
4. 从自选页面查看最近收盘、RSI 和最近条件观察价。点击 ETF 名称查看 K 线/成交量/RSI、六级区间、规则版本及更新状态。
5. 点击「更新行情」或重新打开页面时，后台按 10 分钟冷却策略检查新数据，失败不会清空已有缓存。
6. 在「策略规则」可编辑六类差异化候选模板。规则升级会创建新版本及新的指标/区间快照，不会覆盖旧版本记录。

## 指标、观察价和数据可靠性

- RSI14 使用 Wilder 平滑，MA20 为简单平均，BOLL20 使用总体标准差。
- 初次采集约两年日线，随后回拉最近 45 天并追踪修订；同一交易日数据按交易所、数据源、复权口径、日期去重。
- 策略来自 `backend/app/strategies.py`，债券默认不启用方向性观察，未分类品种只存行情，不给方向性信号。
- 次日观察价每次向历史序列追加 **一个假设下一日收盘价**，全部动态重算；搜索默认前收盘价的 70%~130%，每档 0.001，最大 5 万档。结果为 `BOUNDED_EXHAUSTIVE`（仅指定范围内穷举），不是无限区间精确解。
- `CONFIRMED` 只可能在至少间隔 10 分钟的重复采样、且行情日期早于北京时间当前日期之后出现；这是启发式稳定性规则，仍**不是独立供应商的终值认证**。新的行情标记 `PENDING`，过期缓存标记 `STALE`。
- 当前仅支持 `RAW` 未复权，**尚未建立除息、拆分检测与交易所原始价格交叉校验**，因此观察价明确标注 `RAW_THEORETICAL`。

## 测试与开发

```bash
cd backend
python -m pip install -e '.[test]'
pytest -q
alembic upgrade head
uvicorn app.main:app --reload
```

```bash
cd frontend
npm install
npm run typecheck
npm run build
npm run dev
```

前端开发服务器将 `/api` 转发到后端 8000 端口。正式部署使用 `docker compose`。

## 路线及公开许可

目前已实现主要的 Web/API、SQLite、六类规则、核心条件求解、基础认证和单 worker 按需更新；仍需在真实网络验证 AKShare 接口稳定性、假期和行情确认规则、ETF 公司行动及跨平台 Docker 构建。数据使用授权应由用户遵守供应商条款，软件 MIT 许可**不涵盖任何第三方行情数据**。

仓库公开，但 `.env`、数据库、密码与密钥不应提交。请勿将系统直接开放到公网。
