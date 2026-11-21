export const CATEGORY_NAMES: Record<string,string> = {
  broad:'宽基股票', dividend_low_vol:'红利低波', sector:'行业主题',
  cross_border:'跨境股票', bond:'债券', gold:'黄金'
}
export const LEVELS=['B1','B2','B3','S1','S2','S3'] as const
export type Indicators={rsi14:number;ma20:number;boll_upper:number;boll_lower:number}
export type Region={from:string;to:string;inclusive:boolean;nearest:string;change_pct:number}
export type Thresholds={status:string;intervals:Record<string,Region[]>;searched_range?:string[];price_basis?:string;limit?:string}
export type ETF={symbol:string;name:string;full_name?:string|null;market_name?:string|null;exchange:string;category:string|null;signals_enabled:boolean;rule_version:number;close:number|null;date:string|null;pending_date?:string|null;data_status:string;indicators:Indicators|null;signal:string;thresholds:Thresholds|null}
export type SearchResult={symbol:string;name:string;full_name?:string|null;market_name?:string|null;category:string|null;exchange:string;source:string}
export type Bar={date:string;open:number;high:number;low:number;close:number;volume:number;status:string}
export type HistoryIndicator=Indicators & {date:string;signal:string;rule_version:number}
export type Template={category:string;version:number;params:{buy_rsi:number[];sell_rsi:number[];boll_k:number;extreme_deviation:number;enabled:boolean}}
export type Run={id:number;status:string;message:string|null;started_at:string;finished_at:string|null}
