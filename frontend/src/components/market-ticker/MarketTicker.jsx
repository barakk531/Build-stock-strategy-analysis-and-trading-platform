import { useQuery } from '@tanstack/react-query'
import { useEffect, useState } from 'react'
import { getMarketTicker } from '../../api/marketTicker.js'
import MarketTickerItem from './MarketTickerItem.jsx'
import './MarketTicker.css'

// Daily-close data, so a long refresh is plenty; the backend reads the DB only,
// so this never triggers Yahoo requests.
const REFRESH_MS = 10 * 60 * 1000 // 10 minutes

export default function MarketTicker() {
  const { data, isError, isPending } = useQuery({
    queryKey: ['market-ticker'],
    queryFn: () => getMarketTicker({ limit: 30 }),
    refetchInterval: REFRESH_MS,
    staleTime: REFRESH_MS,
    refetchOnWindowFocus: false,
  })

  // Pause the animation while the tab is hidden (no off-screen work).
  const [tabHidden, setTabHidden] = useState(false)
  useEffect(() => {
    const onVisibility = () => setTabHidden(document.hidden)
    document.addEventListener('visibilitychange', onVisibility)
    return () => document.removeEventListener('visibilitychange', onVisibility)
  }, [])

  const items = Array.isArray(data) ? data : []
  const unavailable = isError || (!isPending && items.length === 0)

  return (
    <div className="mkt-ticker" aria-label="Market ticker, latest daily prices">
      <div className="mkt-ticker__label">
        <span className="mkt-ticker__market">MARKET</span>
        {!unavailable && (
          <span
            className="mkt-ticker__note"
            title="End-of-day prices from Yahoo Finance; may be delayed. Not real-time."
          >
            Latest market data
          </span>
        )}
      </div>

      {unavailable ? (
        <span className="mkt-ticker__message" role="status">
          Market data is currently unavailable
        </span>
      ) : items.length === 0 ? (
        <span className="mkt-ticker__message">Loading latest market data…</span>
      ) : (
        <div className="mkt-ticker__viewport">
          {/* The track is never re-keyed on refresh, so the CSS animation is not
              restarted when the data updates; only the cell values change. */}
          <div className={`mkt-ticker__track${tabHidden ? ' is-paused' : ''}`}>
            {items.map((item) => (
              <MarketTickerItem key={item.symbol} item={item} />
            ))}
            {/* Duplicate copy makes the -50% translate loop seamlessly. */}
            {items.map((item) => (
              <MarketTickerItem key={`dup-${item.symbol}`} item={item} ariaHidden />
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
