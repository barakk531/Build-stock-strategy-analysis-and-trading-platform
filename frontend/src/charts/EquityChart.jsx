import { AreaSeries, createChart, LineSeries } from 'lightweight-charts'
import { useEffect, useRef } from 'react'

// Equity + benchmark share pane 0; drawdown gets its own thin pane below so a
// deep drawdown never distorts the equity scale.
const COLORS = {
  equity: '#34d399',
  benchmark: '#94a3b8',
  drawdown: '#f87171',
  grid: '#1e293b',
  text: '#94a3b8',
}

export default function EquityChart({ equity, benchmark, drawdown }) {
  const containerRef = useRef(null)
  const chartRef = useRef(null)
  const seriesRef = useRef({})

  useEffect(() => {
    const chart = createChart(containerRef.current, {
      autoSize: true,
      layout: {
        background: { color: 'transparent' },
        textColor: COLORS.text,
        panes: { separatorColor: COLORS.grid },
      },
      grid: {
        vertLines: { color: COLORS.grid },
        horzLines: { color: COLORS.grid },
      },
      crosshair: { mode: 0 },
      timeScale: { borderColor: COLORS.grid },
      rightPriceScale: { borderColor: COLORS.grid },
    })

    const equitySeries = chart.addSeries(LineSeries, {
      color: COLORS.equity,
      lineWidth: 2,
      priceLineVisible: false,
    })
    const benchmarkSeries = chart.addSeries(LineSeries, {
      color: COLORS.benchmark,
      lineWidth: 1,
      lineStyle: 1,
      priceLineVisible: false,
      lastValueVisible: false,
    })
    const drawdownSeries = chart.addSeries(
      AreaSeries,
      {
        lineColor: COLORS.drawdown,
        topColor: 'rgba(248, 113, 113, 0.04)',
        bottomColor: 'rgba(248, 113, 113, 0.35)',
        lineWidth: 1,
        priceLineVisible: false,
        lastValueVisible: false,
      },
      1,
    )
    chart.panes()[1]?.setHeight(90)

    chartRef.current = chart
    seriesRef.current = { equitySeries, benchmarkSeries, drawdownSeries }
    return () => {
      chart.remove()
      chartRef.current = null
    }
  }, [])

  useEffect(() => {
    const s = seriesRef.current
    if (!chartRef.current || !s.equitySeries) return
    s.equitySeries.setData(equity ?? [])
    s.benchmarkSeries.setData(benchmark ?? [])
    s.drawdownSeries.setData(drawdown ?? [])
    chartRef.current.timeScale().fitContent()
  }, [equity, benchmark, drawdown])

  return <div ref={containerRef} className="h-[380px] w-full" />
}
