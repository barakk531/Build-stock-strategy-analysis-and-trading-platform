import {
  CandlestickSeries,
  createChart,
  createSeriesMarkers,
  HistogramSeries,
  LineSeries,
} from 'lightweight-charts'
import { useEffect, useRef } from 'react'

// Market-convention colors on the dark theme; SMAs stay distinguishable
// (amber/sky/violet) without stealing attention from price.
const COLORS = {
  up: '#34d399',
  down: '#f87171',
  sma20: '#fbbf24',
  sma50: '#38bdf8',
  sma150: '#a78bfa',
  volume: '#475569',
  avgVolume: '#94a3b8',
  grid: '#1e293b',
  text: '#94a3b8',
}

export default function PriceChart({ candles, smas, volume, markers, show }) {
  const containerRef = useRef(null)
  const chartRef = useRef(null)
  const seriesRef = useRef({})

  // Create once; StrictMode double-mount is handled by the cleanup.
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

    const candleSeries = chart.addSeries(CandlestickSeries, {
      upColor: COLORS.up,
      downColor: COLORS.down,
      wickUpColor: COLORS.up,
      wickDownColor: COLORS.down,
      borderVisible: false,
    })
    const sma20 = chart.addSeries(LineSeries, {
      color: COLORS.sma20, lineWidth: 1, priceLineVisible: false, lastValueVisible: false,
    })
    const sma50 = chart.addSeries(LineSeries, {
      color: COLORS.sma50, lineWidth: 1, priceLineVisible: false, lastValueVisible: false,
    })
    const sma150 = chart.addSeries(LineSeries, {
      color: COLORS.sma150, lineWidth: 2, priceLineVisible: false, lastValueVisible: false,
    })
    const volumeSeries = chart.addSeries(
      HistogramSeries,
      { color: COLORS.volume, priceFormat: { type: 'volume' }, priceLineVisible: false },
      1,
    )
    const avgVolumeSeries = chart.addSeries(
      LineSeries,
      { color: COLORS.avgVolume, lineWidth: 1, priceLineVisible: false, lastValueVisible: false },
      1,
    )
    chart.panes()[1]?.setHeight(110)

    const markerPlugin = createSeriesMarkers(candleSeries, [])

    chartRef.current = chart
    seriesRef.current = { candleSeries, sma20, sma50, sma150, volumeSeries, avgVolumeSeries, markerPlugin }
    return () => {
      chart.remove()
      chartRef.current = null
    }
  }, [])

  // Push data + visibility on every change.
  useEffect(() => {
    const s = seriesRef.current
    if (!chartRef.current || !s.candleSeries) return

    s.candleSeries.setData(candles ?? [])
    s.sma20.setData(show.sma20 ? (smas?.sma20 ?? []) : [])
    s.sma50.setData(show.sma50 ? (smas?.sma50 ?? []) : [])
    s.sma150.setData(show.sma150 ? (smas?.sma150 ?? []) : [])
    s.volumeSeries.setData(show.volume ? (volume?.bars ?? []) : [])
    s.avgVolumeSeries.setData(show.volume ? (volume?.average ?? []) : [])

    const visible = (markers ?? []).filter(
      (m) => (m.signalType === 'BUY' && show.buys) || (m.signalType === 'SELL' && show.sells),
    )
    s.markerPlugin.setMarkers(
      visible.map((m) => ({
        time: m.time,
        position: m.signalType === 'BUY' ? 'belowBar' : 'aboveBar',
        color: m.signalType === 'BUY' ? COLORS.up : COLORS.down,
        shape: m.signalType === 'BUY' ? 'arrowUp' : 'arrowDown',
        text: `${m.signalType === 'BUY' ? 'B' : 'S'} ${m.price ?? ''}`,
      })),
    )
    chartRef.current.timeScale().fitContent()
  }, [candles, smas, volume, markers, show])

  return <div ref={containerRef} className="h-[460px] w-full" />
}
