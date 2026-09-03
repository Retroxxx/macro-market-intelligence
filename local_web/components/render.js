const fmt = value => value == null ? '—' : typeof value === 'number' ? value.toFixed(2) : value
const pct = value => value == null ? '—' : `${(Number(value) * 100).toFixed(1)}%`
const esc = value => String(value ?? '').replace(/[&<>"']/g, char => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]))

export function renderRegime(value) {
  const regime = value.regime || {}
  document.querySelector('#regime').innerHTML = `<div><span class="eyebrow">CURRENT REGIME</span><h2>${esc(regime.regime || 'UNKNOWN')}</h2><p>${esc((regime.evidence || []).join(' · ') || '暂无足够证据')}</p></div><strong class="confidence">${Math.round((regime.confidence || 0) * 100)}<small>% confidence</small></strong>`
}

export function renderStyles(items) {
  document.querySelector('#styles').innerHTML = (items || []).map(item => `<div class="style-row"><span>${esc(item.style_name)}</span><b class="${String(item.direction).toLowerCase()}">${esc(item.state)}</b><small>${item.strength == null ? '无可靠代理' : `${fmt(item.strength)}%`}</small></div>`).join('') || '<p class="muted">暂无风格数据</p>'
}

export function renderHealth(value) {
  const quality = value.data_quality || {}
  const providers = quality.providers || value.data_freshness?.providers || {}
  const providerRows = Object.entries(providers).map(([name, info]) => {
    const status = info?.status || 'UNKNOWN'
    const error = info?.error || (info?.errors ? Object.values(info.errors).join(', ') : '')
    return `<div><dt>${esc(name)}</dt><dd>${esc(status)}${error ? ` · ${esc(error)}` : ''}</dd></div>`
  }).join('')
  const reasonValues = Array.isArray(quality.reasons) ? quality.reasons : quality.reason ? [quality.reason] : []
  const reasons = reasonValues.join(' · ')
  document.querySelector('#health').innerHTML = `<dl><div><dt>Sources</dt><dd>${quality.sources_ok ?? 0} / ${quality.sources_total ?? 0}</dd></div><div><dt>Market status</dt><dd>${esc(value.market_status || '—')}</dd></div><div><dt>Generated</dt><dd>${esc(value.timestamp || '—')}</dd></div><div><dt>Schema</dt><dd>${esc(value.context_version || '—')}</dd></div>${providerRows}${reasons ? `<div><dt>Reasons</dt><dd>${esc(reasons)}</dd></div>` : ''}</dl>`
}

export function renderInternals(value) {
  const breadth = value.breadth || {}
  const pools = value.risk || {}
  document.querySelector('#internals').innerHTML = `<dl><div><dt>Advance ratio</dt><dd>${pct(breadth.advance_ratio)}</dd></div><div><dt>Limit up / down</dt><dd>${fmt(breadth.limit_up)} / ${fmt(breadth.limit_down)}</dd></div><div><dt>Broken rate</dt><dd>${pct(breadth.broken_rate ?? pools.broken_limit_rate)}</dd></div><div><dt>Yesterday continuation</dt><dd>${pct(breadth.yesterday_limit_up_success_rate ?? pools.yesterday_limit_up_continuation)}</dd></div><div><dt>Turnover</dt><dd>${fmt(breadth.turnover ?? value.liquidity?.actual_turnover_yi)}</dd></div></dl>`
}

export function renderSectors(items, timestamp) {
  document.querySelector('#sector-meta').textContent = timestamp || ''
  document.querySelector('#sectors').innerHTML = items?.length ? `<table><thead><tr><th>Sector</th><th>State</th><th>1D</th><th>Breadth</th><th>1D flow</th><th>5D flow</th><th>10D flow</th><th>Persistence</th><th>Quality</th></tr></thead><tbody>${items.map(item => `<tr><td>${esc(item.sector)}</td><td><b>${esc(item.state)}</b></td><td class="${String(item.direction).toLowerCase()}">${fmt(item.relative_strength)}%</td><td>${pct(item.breadth)}</td><td>${fmt(item.flow_1d)}</td><td>${fmt(item.flow_5d)}</td><td>${fmt(item.flow_10d)}</td><td>${esc(item.persistence || 'UNKNOWN')}</td><td>${esc(item.quality || 'UNKNOWN')}</td></tr>`).join('')}</tbody></table>` : '<p class="muted">暂无行业轮动数据；缺少持续性证据时不会伪造状态。</p>'
}
