import {test, expect, type APIRequestContext, type Page} from '@playwright/test'

const symbols=['510300','159915','159307']

async function removeAll(request:APIRequestContext){
  for(const symbol of symbols){
    const response=await request.delete(`/api/v1/watchlist/${symbol}`)
    expect([200,404]).toContain(response.status())
  }
}

async function waitForRun(request:APIRequestContext, previousId=0){
  const deadline=Date.now()+25_000
  while(Date.now()<deadline){
    const response=await request.get('/api/v1/data/runs')
    expect(response.ok()).toBeTruthy()
    const runs=await response.json() as Array<{id:number;status:string;message:string|null}>
    const run=runs.find(item=>item.id>previousId)
    if(run&&['SUCCESS','PARTIAL','FAILED'].includes(run.status))return run
    await new Promise(resolve=>setTimeout(resolve,250))
  }
  throw new Error('等待行情刷新任务超时')
}

async function openAddDialog(page:Page){
  const button=page.getByRole('button',{name:'＋ 添加 ETF'}).first()
  await button.click()
  const dialog=page.getByRole('dialog',{name:'添加 ETF 自选'})
  await expect(dialog).toBeVisible()
  return {button,dialog,input:dialog.getByPlaceholder('例如 510300 或 159307')}
}

async function search(page:Page, code:string){
  const {dialog,input}=await openAddDialog(page)
  await input.fill(code)
  await input.press('Enter')
  await expect(dialog.getByRole('button',{name:new RegExp(code)})).toBeVisible()
  return {dialog,input}
}

test.describe('ETF Signal Lab 完整浏览器验收',()=>{
  test.describe.configure({mode:'serial'})

  test.beforeEach(async({page,request})=>{
    await removeAll(request)
    await page.goto('/')
    await expect(page.getByRole('heading',{name:'自选 ETF 观察台'})).toBeVisible()
  })

  test('免登录打开并支持粘贴、Enter、Escape、遮罩关闭与焦点恢复',async({page})=>{
    const {button,dialog,input}=await openAddDialog(page)
    await input.fill('159307')
    await expect(input).toHaveValue('159307')
    await expect(dialog).toBeVisible()
    await input.press('Escape')
    await expect(dialog).toBeHidden()
    await expect(button).toBeFocused()

    const reopened=await openAddDialog(page)
    await reopened.input.fill('159307')
    await page.locator('.modal-backdrop').click({position:{x:5,y:5}})
    await expect(reopened.dialog).toBeHidden()
  })

  test('搜索 159307 展示三个名称并完成添加、刷新和详情验收',async({page,request})=>{
    const {dialog}=await search(page,'159307')
    await expect(dialog).toContainText('博时中证红利低波100ETF')
    await expect(dialog).toContainText('博时中证红利低波动100交易型开放式指数证券投资基金')
    await expect(dialog).toContainText('红利低波100ETF博时')
    await dialog.locator('select').selectOption('dividend_low_vol')
    await dialog.getByRole('button',{name:/159307/}).click()
    await expect(dialog).toBeHidden()
    const run=await waitForRun(request)
    expect(run.status).toBe('SUCCESS')

    await page.reload()
    const row=page.locator('tbody tr').filter({hasText:'159307'})
    await expect(row).toBeVisible()
    await expect(row).toContainText('博时中证红利低波100ETF')
    await expect(row).toContainText('博时中证红利低波动100交易型开放式指数证券投资基金')
    await expect(row).toContainText('红利低波100ETF博时')
    await row.click()
    await expect(page.getByRole('heading',{name:/博时中证红利低波100ETF/})).toBeVisible()
    await expect(page.getByRole('heading',{name:'日 K 线 · MA20 · BOLL · RSI14'})).toBeVisible()
    await expect(page.locator('[aria-label="OHLC蜡烛图、MA20、布林轨道、成交量和RSI"]')).toBeVisible()
    await expect(page.getByText('B1 买入观察')).toBeVisible()
    await expect(page.getByText('PENDING').first()).toBeVisible()

    const bars=await (await request.get('/api/v1/etfs/159307/daily-bars')).json() as Array<Record<string,unknown>>
    expect(bars.length).toBeGreaterThanOrEqual(20)
    expect(bars.at(-1)).toMatchObject({status:'PENDING'})
    expect(Number(bars.at(-1)?.close)).toBeGreaterThan(0)
    const indicators=await (await request.get('/api/v1/etfs/159307/indicators')).json() as Array<Record<string,unknown>>
    expect(indicators.length).toBeGreaterThanOrEqual(20)
    expect(indicators.at(-1)).toHaveProperty('rsi14')
    const threshold=await (await request.get('/api/v1/etfs/159307/next-day-thresholds')).json() as {status:string;intervals:Record<string,unknown[]>}
    expect(threshold.status).not.toBe('UNAVAILABLE')
    expect(Object.keys(threshold.intervals)).toEqual(expect.arrayContaining(['B1','B2','B3','S1','S2','S3']))
  })

  test('510300 和 159915 都能搜索、添加并在刷新后持久化',async({page,request})=>{
    let previousRun=0
    for(const code of ['510300','159915']){
      const {dialog}=await search(page,code)
      await dialog.getByRole('button',{name:new RegExp(code)}).click()
      await expect(dialog).toBeHidden()
      const run=await waitForRun(request,previousRun)
      expect(run.status).toBe('SUCCESS')
      previousRun=run.id
    }
    await page.reload()
    for(const code of ['510300','159915']){
      await expect(page.locator('tbody tr').filter({hasText:code})).toBeVisible()
      const bars=await (await request.get(`/api/v1/etfs/${code}/daily-bars`)).json() as Array<Record<string,unknown>>
      expect(bars.length).toBeGreaterThanOrEqual(20)
      expect(Number(bars[0].open)).toBeGreaterThan(0)
      expect(Number(bars[0].high)).toBeGreaterThanOrEqual(Number(bars[0].low))
    }
  })

  test('策略规则、数据系统和移动端布局可用',async({page})=>{
    await page.getByRole('button',{name:/策略规则/}).click()
    await expect(page.getByRole('heading',{name:'六类 ETF 策略'})).toBeVisible()
    for(const name of ['宽基股票','红利低波','行业主题','跨境股票','债券','黄金']){
      await expect(page.getByText(name,{exact:true}).first()).toBeVisible()
    }
    await page.getByRole('button',{name:/数据与系统/}).click()
    await expect(page.getByRole('heading',{name:'数据与系统'})).toBeVisible()
    await expect(page.getByText('e2e_fixture',{exact:true})).toBeVisible()
    await page.setViewportSize({width:390,height:844})
    await page.getByRole('button',{name:/自选总览/}).click()
    await expect(page.getByRole('heading',{name:'自选 ETF 观察台'})).toBeVisible()
    const width=await page.evaluate(()=>document.documentElement.scrollWidth)
    expect(width).toBeLessThanOrEqual(390)
    const {dialog}=await openAddDialog(page)
    await expect(dialog).toBeVisible()
  })

  test('搜索上游失败时保留弹窗并显示可见错误',async({page})=>{
    await page.route('**/api/v1/etfs/search?*',route=>route.fulfill({
      status:502,
      contentType:'application/json',
      body:JSON.stringify({detail:'测试上游限流'}),
    }))
    const {dialog,input}=await openAddDialog(page)
    await input.fill('159307')
    await input.press('Enter')
    await expect(page.getByRole('status')).toContainText('测试上游限流')
    await expect(dialog).toBeVisible()
  })
})
