const fmt = value => value == null ? '—' : typeof value === 'number' ? value.toFixed(2) : value
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
  document.querySelector('#health').innerHTML = `<dl><div><dt>Sources</dt><dd>${quality.sources_ok ?? 0} / ${quality.sources_total ?? 0}</dd></div><div><dt>Market status</dt><dd>${esc(value.market_status || '—')}</dd></div><div><dt>Generated</dt><dd>${esc(value.timestamp || '—')}</dd></div><div><dt>Schema</dt><dd>${esc(value.context_version || '—')}</dd></div></dl>`
}

export function renderSectors(items, timestamp) {
  document.querySelector('#sector-meta').textContent = timestamp || ''
  document.querySelector('#sectors').innerHTML = items?.length ? `<table><thead><tr><th>Sector</th><th>State</th><th>Direction</th><th>Relative strength</th><th>Persistence</th></tr></thead><tbody>${items.map(item => `<tr><td>${esc(item.sector)}</td><td><b>${esc(item.state)}</b></td><td class="${String(item.direction).toLowerCase()}">${esc(item.direction)}</td><td>${fmt(item.relative_strength)}%</td><td>${item.persistence == null ? 'UNKNOWN' : fmt(item.persistence)}</td></tr>`).join('')}</tbody></table>` : '<p class="muted">暂无行业轮动数据；缺少持续性证据时不会伪造状态。</p>'
}
