// @vitest-environment jsdom
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest'
import {cleanup, render, screen, waitFor} from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import {App} from './App'
import type {SearchResult} from './types'

const apiMock=vi.hoisted(()=>({
  etfs:vi.fn(async()=>[]),
  search:vi.fn(async(_query:string,_offset=0,_limit=100):Promise<SearchResult[]>=>[]),
  searchStatus:vi.fn(async()=>({source:'TEST',warning:null})),
  add:vi.fn(async()=>({})),
  remove:vi.fn(async()=>({})),
  update:vi.fn(async()=>({})),
  bars:vi.fn(async()=>[]),
  indicators:vi.fn(async()=>[]),
  templates:vi.fn(async()=>[]),
  updateTemplate:vi.fn(async()=>({})),
  refresh:vi.fn(async()=>({run_id:null,status:'ALREADY_RUNNING_OR_EMPTY'})),
  runs:vi.fn(async()=>[]),
  system:vi.fn(async()=>({app_version:'0.1.0',provider:{status:'AVAILABLE_UNTESTED'},latest_run:null,confirmation_notice:''}))
}))

vi.mock('./api',async()=>{
  const actual=await vi.importActual<typeof import('./api')>('./api')
  return {...actual,api:apiMock}
})
vi.mock('./chart',()=>({CandleChart:()=>null}))

describe('ETF panel interaction',()=>{
  beforeEach(()=>{
    apiMock.etfs.mockResolvedValue([])
    apiMock.search.mockResolvedValue([])
    apiMock.searchStatus.mockResolvedValue({source:'TEST',warning:null})
    localStorage.clear()
  })
  afterEach(()=>{cleanup();vi.clearAllMocks()})

  it('opens the LAN panel without a login screen',async()=>{
    render(<App/>)
    expect(await screen.findByText('自选 ETF 观察台')).toBeTruthy()
    expect(screen.queryByText('管理员密码')).toBeNull()
  })

  it('keeps the search dialog open while pasting a code',async()=>{
    const user=userEvent.setup()
    render(<App/>)
    await user.click(screen.getByRole('button',{name:'＋ 添加 ETF'}))
    const input=screen.getByPlaceholderText('例如 510300 或 159307')
    await user.click(input)
    await user.paste('159307')
    expect(screen.getByRole('dialog')).toBeTruthy()
    expect((input as HTMLInputElement).value).toBe('159307')
  })

  it('renders the short, full and market names from search results',async()=>{
    apiMock.search.mockResolvedValue([{
      symbol:'159307',name:'博时中证红利低波100ETF',
      full_name:'博时中证红利低波动100交易型开放式指数证券投资基金',
      market_name:'红利低波100ETF博时',category:null,exchange:'SZ',source:'AKSHARE_EM'
    }])
    const user=userEvent.setup()
    render(<App/>)
    await user.click(screen.getByRole('button',{name:'＋ 添加 ETF'}))
    await user.type(screen.getByPlaceholderText('例如 510300 或 159307'),'159307')
    await user.click(screen.getByRole('button',{name:'搜索'}))
    await waitFor(()=>expect(screen.getByText('博时中证红利低波100ETF')).toBeTruthy())
    expect(screen.getByText('博时中证红利低波动100交易型开放式指数证券投资基金')).toBeTruthy()
    expect(screen.getByText('红利低波100ETF博时')).toBeTruthy()
  })
})
