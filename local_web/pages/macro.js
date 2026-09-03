import { getContext } from '../services/api.js'
import { renderHealth, renderInternals, renderRegime, renderSectors, renderStyles } from '../components/render.js'

export async function loadMacroPage() {
  const status = document.querySelector('#status')
  try {
    const value = await getContext()
    renderRegime(value)
    renderStyles(value.style)
    renderHealth(value)
    renderInternals(value)
    renderSectors(value.sector_rotation, value.timestamp)
    status.textContent = `Updated ${value.timestamp || '—'} · ${value.data_quality?.degraded ? 'degraded / fail-safe' : 'official sources available'}`
    status.className = `status ${value.data_quality?.degraded ? 'warning' : 'ok'}`
  } catch {
    status.textContent = 'Market context unavailable · fail-safe UNKNOWN'
    status.className = 'status warning'
  }
}
