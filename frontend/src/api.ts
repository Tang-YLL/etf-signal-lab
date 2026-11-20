import type {Bar, ETF, HistoryIndicator, Run, Template} from './types'

export class ApiError extends Error { constructor(public status:number, message:string){ super(message) } }
export async function request<T>(path:string, options:RequestInit={}) : Promise<T> {
  const response=await fetch('/api/v1'+path,{credentials:'same-origin',...options,headers:{'Content-Type':'application/json','X-Requested-With':'ETFSignalLab',...options.headers}})
  const data=await response.json().catch(()=>null)
  if(!response.ok)throw new ApiError(response.status, data?.detail || 'Request failed')
  return data as T
}
export const api={
  me:()=>request<{logged_in:boolean}>('/auth/me'),
  login:(password:string)=>request('/auth/login',{method:'POST',body:JSON.stringify({username:'admin',password})}),
  logout:()=>request('/auth/logout',{method:'POST'}),
  changePassword:(old_password:string,new_password:string)=>request('/auth/change-password',{method:'POST',body:JSON.stringify({old_password,new_password})}),
  etfs:()=>request<ETF[]>('/etfs'),
  search:(q:string)=>request<{symbol:string;name:string;category:string|null;source:string}[]>('/etfs/search?q='+encodeURIComponent(q)),
  add:(symbol:string,name:string,category:string|null)=>request<ETF>('/watchlist',{method:'POST',body:JSON.stringify({symbol,name,category})}),
  remove:(symbol:string)=>request('/watchlist/'+symbol,{method:'DELETE'}),
  update:(symbol:string,patch:{category?:string;signals_enabled?:boolean})=>request<ETF>('/etfs/'+symbol,{method:'PATCH',body:JSON.stringify(patch)}),
  bars:(symbol:string)=>request<Bar[]>('/etfs/'+symbol+'/daily-bars'),
  indicators:(symbol:string)=>request<HistoryIndicator[]>('/etfs/'+symbol+'/indicators'),
  templates:()=>request<Template[]>('/strategy/templates'),
  updateTemplate:(category:string,params:Template['params'])=>request('/strategy/templates/'+category,{method:'PUT',body:JSON.stringify(params)}),
  refresh:(symbol?:string)=>request<{run_id:number|null;status:string}>('/data/refresh'+(symbol?'/'+symbol:''),{method:'POST'}),
  runs:()=>request<Run[]>('/data/runs'),
  system:()=>request<{app_version:string;provider:{status:string;package_version?:string};latest_run:Run|null;confirmation_notice:string}>('/system/status')
}
