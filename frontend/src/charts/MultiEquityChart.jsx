import { createChart, LineSeries } from 'lightweight-charts'
import { useEffect, useRef } from 'react'
import { SERIES_COLORS } from '../utils/colors.js'

// Rebased (100 = window start) comparison: one line per account in pane 0,
// matching drawdown lines in a thin pane 1, benchmark dashed grey.
const GRID = '#1e293b'
const TEXT = '#94a3b8'

export default function MultiEquityChart({ series, drawdowns, benchmark }) {
  const containerRef = useRef(null)
  const chartRef = useRef(null)

  // Series count varies per competition — rebuild on every data change.
  useEffect(() => {
    const chart = createChart(containerRef.current, {
      autoSize: true,
      layout: {
        background: { color: 'transparent' },
        textColor: TEXT,
        panes: { separatorColor: GRID },
      },
      grid: { vertLines: { color: GRID }, horzLines: { color: GRID } },
      crosshair: { mode: 0 },
      timeScale: { borderColor: GRID },
      rightPriceScale: { borderColor: GRID },
    })
    chartRef.current = chart

    for (const [i, s] of (series ?? []).entries()) {
      const line = chart.addSeries(LineSeries, {
        color: SERIES_COLORS[i % SERIES_COLORS.length],
        lineWidth: 2,
        priceLineVisible: false,
        title: s.name,
      })
      line.setData(s.points)
    }
    if (benchmark?.length) {
      const bench = chart.addSeries(LineSeries, {
        color: '#94a3b8',
        lineWidth: 1,
        lineStyle: 1,
        priceLineVisible: false,
        lastValueVisible: false,
        title: 'Benchmark',
      })
      bench.setData(benchmark)
    }
    for (const [i, s] of (drawdowns ?? []).entries()) {
      const line = chart.addSeries(
        LineSeries,
        {
          color: SERIES_COLORS[i % SERIES_COLORS.length],
          lineWidth: 1,
          priceLineVisible: false,
          lastValueVisible: false,
        },
        1,
      )
      line.setData(s.points)
    }
    chart.panes()[1]?.setHeight(90)
    chart.timeScale().fitContent()

    return () => {
      chart.remove()
      chartRef.current = null
    }
  }, [series, drawdowns, benchmark])

  return <div ref={containerRef} className="h-[400px] w-full" />
}
