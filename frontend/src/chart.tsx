import {useEffect,useRef} from 'react'
import * as echarts from 'echarts'
import type {Bar,HistoryIndicator,Thresholds} from './types'

const buyColor='#32bfa5',sellColor='#f28b72'
export function CandleChart({bars,indicators,thresholds,dark}:{bars:Bar[];indicators:HistoryIndicator[];thresholds:Thresholds|null;dark:boolean}){
  const container=useRef<HTMLDivElement>(null)
  useEffect(()=>{
    if(!container.current)return
    const chart=echarts.init(container.current,dark?'dark':undefined,{renderer:'canvas'})
    const dates=bars.map(x=>x.date)
    const indexed=new Map(indicators.map(x=>[x.date,x]))
    const line=(key:'ma20'|'boll_upper'|'boll_lower')=>bars.map(x=>indexed.get(x.date)?.[key]??null)
    const colors=bars.map(x=>x.close>=x.open?buyColor:sellColor)
    const regions=thresholds?.intervals??{}
    const marks=Object.entries(regions).flatMap(([key,items])=>items.slice(0,1).map(item=>({name:key,yAxis:Number(item.nearest),lineStyle:{color:key.startsWith('B')?buyColor:sellColor,type:'dashed' as const,width:1},label:{formatter:key+' '+item.nearest,position:'insideEndTop' as const}})))
    const option:echarts.EChartsOption={
      backgroundColor:'transparent',animation:false,
      legend:{top:5,textStyle:{color:dark?'#aab7c8':'#516070'},data:['日K','MA20','BOLL上轨','BOLL下轨','成交量','RSI14']},
      tooltip:{trigger:'axis',axisPointer:{type:'cross'},backgroundColor:dark?'#1f2c3e':'#fff',textStyle:{color:dark?'#fff':'#111827'}},
      axisPointer:{link:[{xAxisIndex:[0,1,2]}]},
      grid:[{left:62,right:54,top:43,height:'53%'},{left:62,right:54,top:'65%',height:'12%'},{left:62,right:54,top:'81%',height:'14%'}],
      xAxis:[0,1,2].map((index)=>({type:'category' as const,data:dates,gridIndex:index,scale:true,boundaryGap:true,axisLabel:{show:index===2,color:dark?'#8393a8':'#637083'},axisLine:{lineStyle:{color:dark?'#405168':'#c8d2e0'}},axisTick:{show:false}})),
      yAxis:[{scale:true,splitLine:{lineStyle:{color:dark?'#243247':'#eef0f4'}},axisLabel:{color:dark?'#8fa1b6':'#778397'}},
        {gridIndex:1,scale:true,splitNumber:2,axisLabel:{show:false},splitLine:{show:false}},
        {gridIndex:2,min:0,max:100,interval:50,axisLabel:{color:dark?'#8fa1b6':'#778397'},splitLine:{lineStyle:{color:dark?'#243247':'#eef0f4'}}}],
      dataZoom:[{type:'inside',xAxisIndex:[0,1,2],start:60,end:100},{type:'slider',xAxisIndex:[0,1,2],bottom:0,height:14,start:60,end:100,showDetail:false}],
      series:[
        {name:'日K',type:'candlestick',data:bars.map(x=>[x.open,x.close,x.low,x.high]),itemStyle:{color:buyColor,color0:sellColor,borderColor:buyColor,borderColor0:sellColor},markLine:{symbol:['none','none'],silent:true,data:marks}},
        {name:'MA20',type:'line',data:line('ma20'),showSymbol:false,smooth:false,lineStyle:{color:'#e5b85d',width:1.6},itemStyle:{color:'#e5b85d'}},
        {name:'BOLL上轨',type:'line',data:line('boll_upper'),showSymbol:false,lineStyle:{color:'#8f8df6',width:1.2},itemStyle:{color:'#8f8df6'}},
        {name:'BOLL下轨',type:'line',data:line('boll_lower'),showSymbol:false,lineStyle:{color:'#8f8df6',width:1.2},itemStyle:{color:'#8f8df6'}},
        {name:'成交量',type:'bar',xAxisIndex:1,yAxisIndex:1,data:bars.map((x,i)=>({value:x.volume,itemStyle:{color:colors[i]}}))},
        {name:'RSI14',type:'line',xAxisIndex:2,yAxisIndex:2,data:bars.map(x=>indexed.get(x.date)?.rsi14??null),showSymbol:false,lineStyle:{color:'#62a9ed',width:1.6},itemStyle:{color:'#62a9ed'},markLine:{silent:true,symbol:['none','none'],label:{show:false},data:[{yAxis:30},{yAxis:70}]}}
      ]
    }
    chart.setOption(option)
    const observer=new ResizeObserver(()=>chart.resize())
    observer.observe(container.current)
    return()=>{observer.disconnect();chart.dispose()}
  },[bars,indicators,thresholds,dark])
  return <div ref={container} className="candle-chart" aria-label="OHLC蜡烛图、MA20、布林轨道、成交量和RSI"/>
}
