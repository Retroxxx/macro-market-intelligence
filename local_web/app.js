import { loadMacroPage } from './pages/macro.js'

const fallbackCoreUrl = () => `${window.location.protocol}//${window.location.hostname}:8787/`

const safeCoreUrl = value => {
  try {
    const url = new URL(String(value))
    return ['http:', 'https:'].includes(url.protocol) ? url.href : fallbackCoreUrl()
  } catch {
    return fallbackCoreUrl()
  }
}

async function setCoreLink() {
  const link = document.querySelector('#core-link')
  if (!link) return
  link.href = fallbackCoreUrl()
  const controller = new AbortController()
  const timeout = setTimeout(() => controller.abort(), 3_000)
  try {
    const response = await fetch('/api/local/v1/health', {
      headers: { Accept: 'application/json' },
      signal: controller.signal,
    })
    const health = response.ok ? await response.json() : {}
    link.href = safeCoreUrl(health.niuone_public_url)
  } catch {
    link.href = fallbackCoreUrl()
  } finally {
    clearTimeout(timeout)
  }
}

setCoreLink()
loadMacroPage()
setInterval(loadMacroPage, 60_000)
