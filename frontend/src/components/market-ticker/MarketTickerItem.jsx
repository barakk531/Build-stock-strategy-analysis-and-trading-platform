import { Link } from 'react-router-dom'

function formatPrice(value) {
  return `$${Number(value).toLocaleString('en-US', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })}`
}

// One clickable ticker cell. `ariaHidden` marks the duplicated copy used only
// for the seamless loop so it stays out of the a11y tree and tab order.
export default function MarketTickerItem({ item, ariaHidden = false }) {
  const pct = item.change_percent
  const dir = pct > 0 ? 'up' : pct < 0 ? 'down' : 'flat'
  const arrow = dir === 'up' ? '▲' : dir === 'down' ? '▼' : '·'
  const sign = pct > 0 ? '+' : ''

  return (
    <Link
      to={`/stocks/${item.symbol}`}
      className={`mkt-ticker__item mkt-ticker__item--${dir}`}
      aria-hidden={ariaHidden ? 'true' : undefined}
      tabIndex={ariaHidden ? -1 : undefined}
      title={`${item.symbol} · ${formatPrice(item.price)}`}
    >
      <span className="mkt-ticker__symbol">{item.symbol}</span>
      <span className="mkt-ticker__price">{formatPrice(item.price)}</span>
      <span className="mkt-ticker__arrow">{arrow}</span>
      <span className="mkt-ticker__change">
        {sign}
        {Number(item.change).toFixed(2)}
      </span>
      <span className="mkt-ticker__pct">
        ({sign}
        {Number(pct).toFixed(2)}%)
      </span>
    </Link>
  )
}
