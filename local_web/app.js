import { loadMacroPage } from './pages/macro.js'

document.querySelector('#core-link').href = `${window.location.protocol}//${window.location.hostname}:8787/`
loadMacroPage()
setInterval(loadMacroPage, 60_000)
