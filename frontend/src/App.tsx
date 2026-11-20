import {useCallback,useEffect,useMemo,useState} from 'react'
import {api,ApiError} from './api'
import {CandleChart} from './chart'
import {CATEGORY_NAMES,LEVELS} from './types'
import type {Bar,ETF,HistoryIndicator,Run,Template} from './types'

type Page='dashboard'|'detail'|'rules'|'system'
const money=(x:number|null|undefined)=>x==null?'—':x.toFixed(3)
const percent=(x:number|null|undefined)=>x==null?'—':(x>=0?'+':'')+x.toFixed(2)+'%'
const dateTime=(x:string|null|undefined)=>x?new Date(x).toLocaleString('zh-CN'): '—'
function nearest(etf:ETF,side:'B'|'S'){
  const intervals=etf.thresholds?.intervals
  if(!intervals)return null
  const items=Object.entries(intervals).filter(([key])=>key.startsWith(side)).flatMap(([level,ranges])=>ranges.map(region=>({level,...region})))
  if(!items.length||etf.close==null)return null
  return items.sort((a,b)=>Math.abs(Number(a.nearest)-etf.close!)-Math.abs(Number(b.nearest)-etf.close!))[0]
}

export function App(){
  const [loggedIn,setLoggedIn]=useState<boolean|null>(null)
  const [password,setPassword]=useState('')
  const [error,setError]=useState('')
  const [busy,setBusy]=useState(false)
  const [etfs,setEtfs]=useState<ETF[]>([])
  const [selected,setSelected]=useState<string|null>(null)
  const [page,setPage]=useState<Page>('dashboard')
  const [addOpen,setAddOpen]=useState(false)
  const [query,setQuery]=useState('')
  const [results,setResults]=useState<{symbol:string;name:string;category:string|null;source:string}[]>([])
  const [addCategory,setAddCategory]=useState('broad')
  const [dark,setDark]=useState(localStorage.getItem('etf-theme')!=='light')
  const [filter,setFilter]=useState('all')
  const [sort,setSort]=useState('symbol')
  const [bars,setBars]=useState<Bar[]>([])
  const [history,setHistory]=useState<HistoryIndicator[]>([])
  const [templates,setTemplates]=useState<Template[]>([])
  const [runs,setRuns]=useState<Run[]>([])
  const [system,setSystem]=useState<{provider?:{status:string;package_version?:string};confirmation_notice?:string}|null>(null)
  const [oldPassword,setOldPassword]=useState('')
  const [newPassword,setNewPassword]=useState('')

  useEffect(()=>{document.documentElement.dataset.theme=dark?'dark':'light';localStorage.setItem('etf-theme',dark?'dark':'light')},[dark])
  useEffect(()=>{api.me().then(x=>setLoggedIn(x.logged_in)).catch(()=>setLoggedIn(false))},[])
  const notify=(message:string)=>{setError(message);window.setTimeout(()=>setError(''),7000)}
  const load=useCallback(async()=>{try{setEtfs(await api.etfs())}catch(e){if(e instanceof ApiError&&e.status===401)setLoggedIn(false);else notify(String(e))}},[])
  useEffect(()=>{if(loggedIn){void load();const interval=window.setInterval(()=>void load(),60000);return()=>window.clearInterval(interval)}},[loggedIn,load])
  useEffect(()=>{if(loggedIn&&selected){Promise.all([api.bars(selected),api.indicators(selected)]).then(([b,h])=>{setBars(b);setHistory(h)}).catch(e=>notify(String(e))) }},[loggedIn,selected,etfs])
  useEffect(()=>{if(loggedIn&&page==='rules'){api.templates().then(setTemplates).catch(e=>notify(String(e))) }},[loggedIn,page])
  useEffect(()=>{if(loggedIn&&page==='system'){Promise.all([api.runs(),api.system()]).then(([a,b])=>{setRuns(a);setSystem(b)}).catch(e=>notify(String(e))) }},[loggedIn,page])
  const current=etfs.find(e=>e.symbol===selected)??null
  const filtered=useMemo(()=>etfs.filter(e=>filter==='all'||(filter==='buy'&&e.signal.startsWith('B'))||(filter==='sell'&&e.signal.startsWith('S'))||e.category===filter).sort((a,b)=>sort==='distance'?Math.abs(nearest(a,'B')?.change_pct??999)-Math.abs(nearest(b,'B')?.change_pct??999):sort==='rsi'?(a.indicators?.rsi14??999)-(b.indicators?.rsi14??999):a.symbol.localeCompare(b.symbol)),[etfs,filter,sort])

  async function login(event:React.FormEvent){event.preventDefault();setBusy(true);try{await api.login(password);setPassword('');setLoggedIn(true);setError('')}catch(e){notify(e instanceof Error?e.message:String(e))}finally{setBusy(false)}}
  async function refresh(symbol?:string){setBusy(true);try{const result=await api.refresh(symbol);notify(result.run_id?'已提交后台更新任务，刷新页面查看结果':'已有更新任务运行中');window.setTimeout(()=>void load(),2000)}catch(e){notify(String(e))}finally{setBusy(false)}}
  async function find(){if(!query.trim())return;setBusy(true);try{setResults(await api.search(query.trim()))}catch(e){notify(String(e))}finally{setBusy(false)}}
  async function add(symbol:string,name:string){setBusy(true);try{await api.add(symbol,name,addCategory);setAddOpen(false);setQuery('');await load();notify('已加入自选，后台开始尝试获取行情')}catch(e){notify(String(e))}finally{setBusy(false)}}
  async function remove(symbol:string){if(!confirm('从自选列表移除 '+symbol+'？保留已存历史行情。'))return;try{await api.remove(symbol);setPage('dashboard');setSelected(null);await load()}catch(e){notify(String(e))}}
  async function changeETF(patch:{category?:string;signals_enabled?:boolean}){if(!selected)return;setBusy(true);try{await api.update(selected,patch);await load()}catch(e){notify(String(e))}finally{setBusy(false)}}
  async function saveTemplate(t:Template){setBusy(true);try{await api.updateTemplate(t.category,t.params);notify('策略版本已更新；旧历史规则快照不会被覆盖');await load()}catch(e){notify(String(e))}finally{setBusy(false)}}

  if(loggedIn===null)return <div className="loading">ETF Signal Lab · 正在连接...</div>
  if(!loggedIn)return <main className="login-layout"><section className="login-card"><div className="brand-icon">◆</div><div className="eyebrow">ETF SIGNAL LAB</div><h1>收盘后，看得更清晰。</h1><p>私人 ETF 技术观察台。只查看收盘行情与条件观察价，不执行任何交易。</p><form onSubmit={login}><label>管理员密码</label><input value={password} onChange={e=>setPassword(e.target.value)} type="password" autoComplete="current-password" placeholder="首次启动密码在 backend 容器日志中" required/><button disabled={busy} className="primary">{busy?'正在登录':'进入控制台'}</button></form><small>首次部署：运行 <code>docker compose logs backend</code> 查看随机生成的密码。</small>{error&&<p className="error">{error}</p>}</section></main>
  return <div className="shell">
    <aside className="sidebar"><div className="brand"><span className="brand-mark">◆</span><span>ETF <strong>Signal Lab</strong><small>CONDITION · NOT PREDICTION</small></span></div>
      <div className="nav-caption">工作台</div>
      <button className={page==='dashboard'?'nav active':'nav'} onClick={()=>{setPage('dashboard');setSelected(null)}}>▦ <span>自选总览</span><b>{etfs.length}</b></button>
      <button className={page==='rules'?'nav active':'nav'} onClick={()=>setPage('rules')}>⚙ <span>策略规则</span></button>
      <button className={page==='system'?'nav active':'nav'} onClick={()=>setPage('system')}>◷ <span>数据与系统</span></button>
      <div className="sidebar-bottom"><span className="mini-dot"/> 收盘数据分析 · RAW <div className="sidebar-note">不提供实时交易指令<br/>默认规则未经回测验证</div></div>
    </aside>
    <main className="main">
      <header className="topbar"><div className="breadcrumb">ETF SIGNAL LAB <span>/</span> {page==='dashboard'?'自选总览':page==='detail'?current?.symbol+' 详情':page==='rules'?'策略规则':'数据与系统'}</div><div className="top-actions"><button className="icon-button" title="切换外观" onClick={()=>setDark(!dark)}>{dark?'☼':'☾'}</button><span className="user-mark">ADMIN</span><button className="text-button" onClick={async()=>{await api.logout();setLoggedIn(false)}}>退出</button></div></header>
      {error&&<div role="status" className="toast" onClick={()=>setError('')}>{error} ×</div>}
      {page==='dashboard'&&<>
        <div className="page-heading"><div><span className="eyebrow">MARKET OVERVIEW</span><h1>自选 ETF 观察台</h1><p>历史收盘指标 · 下一交易日条件触发价</p></div><div className="heading-actions"><button className="secondary" onClick={()=>void refresh()} disabled={busy}>↻ 更新行情</button><button className="primary" onClick={()=>setAddOpen(true)}>＋ 添加 ETF</button></div></div>
        <section className="metric-grid"><div className="metric"><div>自选 ETF</div><strong>{etfs.length}</strong><small>仅展示已添加的品种</small></div><div className="metric"><div>买入观察信号</div><strong className="buy-text">{etfs.filter(e=>e.signal.startsWith('B')).length}</strong><small>B1 / B2 / B3</small></div><div className="metric"><div>卖出观察信号</div><strong className="sell-text">{etfs.filter(e=>e.signal.startsWith('S')).length}</strong><small>S1 / S2 / S3</small></div><div className="metric"><div>待确认或过期</div><strong>{etfs.filter(e=>e.data_status!=='CONFIRMED').length}</strong><small>请留意数据日期</small></div></section>
        <section className="panel"><div className="panel-heading"><div><h2>行情与观察价</h2><p>价格变化幅度均相对最近已保存收盘价</p></div><div className="controls"><select value={filter} onChange={e=>setFilter(e.target.value)}><option value="all">全部类型 / 信号</option><option value="buy">买入观察</option><option value="sell">卖出观察</option>{Object.entries(CATEGORY_NAMES).map(([k,v])=><option key={k} value={k}>{v}</option>)}</select><select value={sort} onChange={e=>setSort(e.target.value)}><option value="symbol">按代码</option><option value="distance">买入观察价距离</option><option value="rsi">按 RSI</option></select></div></div>
          <div className="table-scroll"><table><thead><tr><th>ETF</th><th>最近收盘</th><th>RSI14</th><th>当前等级</th><th>最近买入观察价</th><th>最近卖出观察价</th><th>数据状态</th></tr></thead><tbody>{filtered.map(e=>{const b=nearest(e,'B'),s=nearest(e,'S');return <tr key={e.symbol} onClick={()=>{setSelected(e.symbol);setPage('detail')}} tabIndex={0} onKeyDown={evt=>{if(evt.key==='Enter'){setSelected(e.symbol);setPage('detail')}}}><td><strong>{e.name}</strong><small>{e.symbol} · {e.category?CATEGORY_NAMES[e.category]:'未分类'}</small></td><td><strong>{money(e.close)}</strong><small>{e.date||'暂无行情'}</small></td><td>{e.indicators?.rsi14?.toFixed(2)??'—'}</td><td><span className={'signal '+(e.signal.startsWith('B')?'buy':e.signal.startsWith('S')?'sell':'neutral')}>{e.signal}</span></td><td><strong className="buy-text">{b?money(Number(b.nearest)):'—'}</strong><small className="buy-text">{b?`${b.level} · ${percent(b.change_pct)}`:'未发现区间'}</small></td><td><strong className="sell-text">{s?money(Number(s.nearest)):'—'}</strong><small className="sell-text">{s?`${s.level} · ${percent(s.change_pct)}`:'未发现区间'}</small></td><td><span className={'status '+e.data_status.toLowerCase()}>{e.data_status}</span></td></tr>})}</tbody></table>{!filtered.length&&<div className="empty"><div>◇</div><h3>暂无符合条件的 ETF</h3><p>添加基金代码后系统会尝试获取历史日线并计算观察价。</p><button className="primary" onClick={()=>setAddOpen(true)}>添加第一只 ETF</button></div>}</div>
        </section><div className="disclaimer">ⓘ 技术信号仅为候选观察规则，次日观察价是“假定次日按该价格收盘”的条件计算，不是价格预测、买卖建议或收益承诺。未确认行情请勿用于决策。</div>
      </>}
      {page==='detail'&&current&&<><div className="detail-back" onClick={()=>setPage('dashboard')}>← 返回自选总览</div><div className="page-heading"><div><span className="eyebrow">ETF DETAIL / {current.exchange}</span><h1>{current.name} <span className="muted-title">{current.symbol}</span></h1><p>{current.category?CATEGORY_NAMES[current.category]:'未分类'} · 行情日期：{current.date||'暂无'} · {current.data_status}</p></div><div className="heading-actions"><button className="secondary" disabled={busy} onClick={()=>void refresh(current.symbol)}>↻ 更新此 ETF</button><button className="danger-outline" onClick={()=>void remove(current.symbol)}>移出自选</button></div></div>
        <div className="detail-metrics"><div><span>最近收盘</span><strong>{money(current.close)}</strong></div><div><span>RSI14</span><strong>{current.indicators?.rsi14.toFixed(2)||'—'}</strong></div><div><span>MA20</span><strong>{money(current.indicators?.ma20)}</strong></div><div><span>当前观察</span><strong>{current.signal}</strong></div></div>
        <div className="panel chart-panel"><div className="panel-heading"><div><h2>日 K 线 · MA20 · BOLL · RSI14</h2><p>仅使用已保存的实际历史 K 线；虚线为下一交易日条件价</p></div><span className="pill">RAW 未复权</span></div>{bars.length>0?<CandleChart bars={bars} indicators={history} thresholds={current.thresholds} dark={dark}/>:<div className="empty"><h3>暂无历史 K 线</h3><p>点击更新此 ETF 后等待采集完成，数据源可能出现连接失败。</p></div>}</div>
        <section className="panel"><div className="panel-heading"><div><h2>下一交易日条件观察区间</h2><p>根据假定收盘价重算 RSI / MA / BOLL，逐档检验六级规则</p></div><span className="status">{current.thresholds?.status??'UNAVAILABLE'}</span></div><div className="levels">{LEVELS.map(level=>{const regions=current.thresholds?.intervals[level]||[];const region=regions[0];return <div className={'level-card '+(level.startsWith('B')?'buy-border':'sell-border')} key={level}><span>{level} {level.startsWith('B')?'买入观察':'卖出观察'}</span><strong>{region?money(Number(region.nearest)):'—'}</strong><small>{region?percent(region.change_pct):'指定范围内无触发'}</small>{regions.length>1&&<small>共 {regions.length} 个离散区间</small>}</div>})}</div><p className="footnote">范围：{current.thresholds?.searched_range?.join(' ～ ')||'—'}；仅搜索该范围内的有效报价档位，范围外可能有其他解。公司行动、除息、复权转换尚未校验；实际可交易价需自行核实。</p></section>
        <section className="panel"><div className="panel-heading"><h2>ETF 设置</h2></div><div className="settings-inline"><label>所属类别 <select value={current.category||''} onChange={e=>void changeETF({category:e.target.value})}><option value="" disabled>选择类别</option>{Object.entries(CATEGORY_NAMES).map(([k,v])=><option key={k} value={k}>{v}</option>)}</select></label><label className="switch-row"><input type="checkbox" checked={current.signals_enabled} onChange={e=>void changeETF({signals_enabled:e.target.checked})}/> 启用方向性信号</label><span>规则版本：v{current.rule_version}</span></div></section>
      </>}
      {page==='rules'&&<><div className="page-heading"><div><span className="eyebrow">STRATEGY CONFIGURATION</span><h1>六类 ETF 策略</h1><p>候选默认值 · 编辑后会生成新规则版本并重新计算</p></div></div><div className="notice">这些阈值未经历史有效性检验，不代表具有预测能力。债券 ETF 默认关闭方向性观察。</div><div className="rules-grid">{templates.map(t=><div className="panel rule-panel" key={t.category}><div className="rule-header"><h2>{CATEGORY_NAMES[t.category]}</h2><span>v{t.version}</span></div><div className="rule-fields"><label>B1 / B2 / B3 RSI <input value={t.params.buy_rsi.join(', ')} onChange={e=>setTemplates(x=>x.map(v=>v.category===t.category?{...v,params:{...v.params,buy_rsi:e.target.value.split(',').map(Number)}}:v))}/></label><label>S1 / S2 / S3 RSI <input value={t.params.sell_rsi.join(', ')} onChange={e=>setTemplates(x=>x.map(v=>v.category===t.category?{...v,params:{...v.params,sell_rsi:e.target.value.split(',').map(Number)}}:v))}/></label><label>BOLL 倍数 <input type="number" step="0.1" min="0.1" value={t.params.boll_k} onChange={e=>setTemplates(x=>x.map(v=>v.category===t.category?{...v,params:{...v.params,boll_k:Number(e.target.value)}}:v))}/></label><label>极端轨道偏离 (%) <input type="number" min="0" max="49" step="0.1" value={t.params.extreme_deviation*100} onChange={e=>setTemplates(x=>x.map(v=>v.category===t.category?{...v,params:{...v.params,extreme_deviation:Number(e.target.value)/100}}:v))}/></label><label className="switch-row"><input type="checkbox" checked={t.params.enabled} onChange={e=>setTemplates(x=>x.map(v=>v.category===t.category?{...v,params:{...v.params,enabled:e.target.checked}}:v))}/> 启用该模板方向性观察</label></div><button className="secondary" disabled={busy} onClick={()=>void saveTemplate(t)}>保存新版本</button></div>)}</div></>}
      {page==='system'&&<><div className="page-heading"><div><span className="eyebrow">DATA OPERATIONS</span><h1>数据与系统</h1><p>数据状态、采集记录与账号安全</p></div><button className="primary" disabled={busy} onClick={()=>void refresh()}>↻ 更新全部自选</button></div><div className="panel"><div className="panel-heading"><h2>数据提供者</h2></div><div className="system-grid"><div><span>当前提供者</span><strong>AKShare / 东方财富</strong></div><div><span>接入状态</span><strong>{system?.provider?.status||'—'}</strong></div><div><span>AKShare 版本</span><strong>{system?.provider?.package_version||'—'}</strong></div></div><p className="footnote">{system?.confirmation_notice} 数据授权、行情可用性和可复现性需实际验证。</p></div><div className="panel"><div className="panel-heading"><h2>最近更新任务</h2><button className="text-button" onClick={()=>Promise.all([api.runs(),api.system()]).then(([a,b])=>{setRuns(a);setSystem(b)})}>刷新状态</button></div><div className="table-scroll"><table><thead><tr><th>任务</th><th>状态</th><th>开始时间</th><th>完成时间</th><th>结果</th></tr></thead><tbody>{runs.map(r=><tr key={r.id}><td>#{r.id}</td><td>{r.status}</td><td>{dateTime(r.started_at)}</td><td>{dateTime(r.finished_at)}</td><td className="run-message">{r.message||'—'}</td></tr>)}</tbody></table>{!runs.length&&<div className="empty">尚无采集记录</div>}</div></div><div className="panel"><div className="panel-heading"><h2>更改管理员密码</h2></div><form className="password-form" onSubmit={async e=>{e.preventDefault();try{await api.changePassword(oldPassword,newPassword);setOldPassword('');setNewPassword('');notify('密码更新成功')}catch(error){notify(String(error))}}}><input type="password" placeholder="当前密码" value={oldPassword} onChange={e=>setOldPassword(e.target.value)} required/><input type="password" placeholder="新密码（至少12位）" minLength={12} value={newPassword} onChange={e=>setNewPassword(e.target.value)} required/><button className="secondary">更新密码</button></form></div></>}
    </main>
    {addOpen&&<div className="modal-backdrop" onClick={()=>setAddOpen(false)}><section className="modal" onClick={e=>e.stopPropagation()}><div className="modal-heading"><h2>添加 ETF 自选</h2><button className="icon-button" onClick={()=>setAddOpen(false)}>×</button></div><p>输入沪深 ETF 六位代码或名称。若数据源不可用，仍可手动保存准确名称与代码。</p><div className="search-line"><input autoFocus placeholder="例如 510300" value={query} onChange={e=>setQuery(e.target.value)} onKeyDown={e=>{if(e.key==='Enter')void find()}}/><button className="primary" disabled={busy} onClick={()=>void find()}>搜索</button></div><label className="modal-label">选择策略类别 <select value={addCategory} onChange={e=>setAddCategory(e.target.value)}>{Object.entries(CATEGORY_NAMES).map(([k,v])=><option value={k} key={k}>{v}</option>)}</select></label><div className="search-results">{results.map(x=><button className="result" key={x.symbol} onClick={()=>void add(x.symbol,x.name)}><strong>{x.name}</strong><span>{x.symbol} · {x.source}　＋</span></button>)}{!results.length&&<p>未返回搜索结果？若已知准确基金名称与代码，可手动填写下方信息。</p>}</div>{/^\d{6}$/.test(query)&&<button className="secondary full" disabled={busy} onClick={()=>{const name=window.prompt('请输入准确的 ETF 产品名称（不要只填代码）');if(name?.trim())void add(query,name.trim())}}>使用此代码手动添加</button>}</section></div>}
  </div>
}
