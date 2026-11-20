# ETF Signal Lab — V1 验收状态

更新日期：2026-11-20（Asia/Shanghai）。此文件记录真实执行证据，不将自动化测试冒充实际用户环境验收。

## 已实现

- FastAPI + SQLite（WAL）+ SQLAlchemy/Alembic，单 worker 后端。
- React + TypeScript + Apache ECharts（日 K、成交量、MA、BOLL、RSI）。
- 登录、初始化管理员密码、自选增删、六类规则、规则版本与历史信号快照。
- Wilder RSI14 / MA20 / BOLL20、B1–B3 与 S1–S3。
- 指定价格范围内逐最小报价档位的次日条件区间求解（不推断范围外的完整性）。
- Docker Compose + Nginx 非 root + 命名卷持久化 + 健康检查。
- 启动/网页访问/手动触发的按需采集、冷却时间、失败保留缓存、修订记录。
- 东方财富 ETF 名录失败时，经实测验证的新浪名录回退与缓存/30 分钟故障冷却。
- 历史日线始终只从主 AKShare 东方财富接口以 RAW 口径获取；未验证备用日线不混入指标。

## 实测证据

- [CI 成功（含 Docker 构建/启动/HTTP 健康检查/SQLite 重启持久化）](https://github.com/Tang-YLL/etf-signal-lab/actions/runs/44729821421)
- [2026-11-20 首轮实时数据源测试](https://github.com/Tang-YLL/etf-signal-lab/actions/runs/44729556425)：AKShare 1.20.65，沪深 ETF 日线各返回 31 根；ETF 名录 HTTP 502；旧交易日历函数已更名。
- [2026-11-20 二轮实时数据源测试](https://github.com/Tang-YLL/etf-signal-lab/actions/runs/44730040112)：东方财富日线遇到 Push2RateLimitError；新浪 ETF 名录 927 条、代码 510300 可查询；新版新浪交易日历接口可用。
- 单元测试不依赖东方财富网络请求，包含供应商错误、历史数据修订、验证状态、未分类规则、条件价逐档核验等。

## 尚不能宣称完成的验收

1. 实际用户 NAS/Mac/Linux 主机上的网络连通性与浏览器手工端到端操作，以及 Android/iPhone 屏幕尺寸验收。
2. 东方财富接口在真实运行网络中的长期稳定性；临时限流时必须保留已缓存数据并提示失败。
3. 数据最终性：盘后间隔 10 分钟的重复采样只是启发式稳定性检查，不等于交易所/供应商官方终值认证。
4. 除息、基金份额折算、RAW 与前后复权转换及价格变动单位的逐基金核验。
5. 策略阈值的历史有效性验证；所有 B/S 都是**观察条件**，不能当作经过验证的交易建议。
6. 行情供应商的数据授权条款独立核实；MIT 仅覆盖软件代码。

## 个人 LAN 试运行

```bash
git clone https://github.com/Tang-YLL/etf-signal-lab.git
cd etf-signal-lab
cp .env.example .env
docker compose up -d --build
docker compose ps
docker compose logs backend   # 首次登录 admin 密码，勿公开日志
```

浏览器访问 `http://服务器局域网IP:8080`。添加 ETF 后，首次行情可能显示 PENDING；间隔 10 分钟以后重新检查，若主数据源可访问且两次日线一致，则可能进入 CONFIRMED。未确认时可以显示数值指标试算，不显示方向性 B/S 操作信号。

不要对外开放 Web 端口，也不要执行 `docker compose down -v` 删除数据卷。

**发布判断**：目前可供受控 LAN 试运行；在完成上述验证前，不标记为“完全验收通过”。
