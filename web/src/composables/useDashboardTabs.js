import { computed, reactive, ref } from 'vue'

const CATEGORY_ORDER = ['overview', 'practice', 'niuone_mainline', 'indices', 'market_monitor', 'realtime_news', 'dragon_tiger', 'us_ratings']
const CATEGORY_LABELS = {
  overview: '总览',
  practice: '模拟交易',
  niuone_mainline: '题材强度',
  indices: '指数行情',
  market_monitor: '盘面监控',
  realtime_news: '财经快讯',
  dragon_tiger: '龙虎榜',
  us_ratings: '美股机构买入评级',
}
const CATEGORY_PATHS = {
  overview: '/',
  practice: '/practice',
  niuone_mainline: '/niuone-mainline',
  indices: '/indices',
  industry_flow: '/industry-flow',
  market_monitor: '/market-monitor',
  realtime_news: '/realtime-news',
  dragon_tiger: '/dragon-tiger',
  us_ratings: '/us-ratings',
}
const PATH_CATEGORIES = Object.fromEntries(
  Object.entries(CATEGORY_PATHS).map(([category, path]) => [path, category]),
)
const LEGACY_CATEGORY_ALIASES = { b1_screen: 'practice' }
const US_FEATURE_CATEGORIES = new Set(['us_ratings'])
const MESSAGE_COUNT_CATEGORIES = ['market_monitor', 'us_ratings']
const REQUEST_TIMEOUT_MS = 15 * 1000

const initialQueryCategory = new URLSearchParams(window.location.search).get('category') || ''
const initialCategory = dashboardCategoryFromLocation(window.location.pathname, initialQueryCategory)
const activeCategory = ref(initialCategory)
const autoVersionCheckEnabled = ref(true)
const currentVersion = ref('dev')
const usFeaturesEnabled = ref(false)
const bootstrapLoaded = ref(false)
const bootstrapError = ref('')
const countOverrides = reactive({
  market_monitor: '',
  realtime_news: '',
  us_ratings: '',
})
let bootstrapRequest = null

function categoryAvailable(category) {
  return !US_FEATURE_CATEGORIES.has(category) || usFeaturesEnabled.value
}

const items = computed(() => CATEGORY_ORDER
  .filter(categoryAvailable)
  .map(key => ({
    key,
    href: CATEGORY_PATHS[key],
    label: CATEGORY_LABELS[key],
    count: String(countOverrides[key] || ''),
    active: activeCategory.value === key || (activeCategory.value === 'industry_flow' && key === 'indices'),
  })))

export function dashboardCategoryFromLocation(path, queryCategory = '') {
  const normalizedQuery = LEGACY_CATEGORY_ALIASES[queryCategory] || queryCategory
  if (path === '/') {
    const category = normalizedQuery || 'overview'
    return Object.hasOwn(CATEGORY_PATHS, category) ? category : 'overview'
  }
  return PATH_CATEGORIES[path] || ''
}

export function dashboardCategoryPath(category) {
  return CATEGORY_PATHS[LEGACY_CATEGORY_ALIASES[category] || category] || CATEGORY_PATHS.overview
}

function setActiveCategory(category) {
  activeCategory.value = Object.hasOwn(CATEGORY_PATHS, category) ? category : ''
}

function setCategoryCount(category, count) {
  countOverrides[category] = String(count || '')
}

function applyBootstrapCounts(counts) {
  if (!counts || typeof counts !== 'object') return
  for (const category of MESSAGE_COUNT_CATEGORIES) {
    if (!Object.hasOwn(counts, category)) continue
    const count = Number(counts[category])
    if (!Number.isFinite(count)) continue
    setCategoryCount(category, ` · ${Math.max(0, Math.trunc(count))}`)
  }
}

async function initializeDashboardTabs() {
  if (bootstrapLoaded.value) return { usFeaturesEnabled: usFeaturesEnabled.value }
  if (bootstrapRequest) return bootstrapRequest
  const controller = new AbortController()
  const timeout = window.setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS)
  const request = fetch('/api/dashboard/bootstrap', {
    credentials: 'same-origin',
    cache: 'no-store',
    signal: controller.signal,
  }).then(async response => {
    if (!response.ok) throw new Error(`HTTP ${response.status}`)
    const payload = await response.json()
    const bootstrapVersion = String(payload.current_version || '').trim()
    if (bootstrapVersion) currentVersion.value = bootstrapVersion
    autoVersionCheckEnabled.value = payload.auto_version_check_enabled !== false
    usFeaturesEnabled.value = payload.us_features_enabled === true
    applyBootstrapCounts(payload.message_counts)
    bootstrapError.value = ''
    bootstrapLoaded.value = true
    return { ...payload, usFeaturesEnabled: usFeaturesEnabled.value }
  }).catch(error => {
    if (error?.name === 'AbortError') bootstrapError.value = '栏目配置请求超时'
    else bootstrapError.value = String(error?.message || error)
    bootstrapLoaded.value = true
    return { usFeaturesEnabled: false, error: bootstrapError.value }
  }).finally(() => {
    window.clearTimeout(timeout)
    if (bootstrapRequest === request) bootstrapRequest = null
  })
  bootstrapRequest = request
  return request
}

export function useDashboardTabs() {
  return {
    activeCategory,
    autoVersionCheckEnabled,
    bootstrapError,
    bootstrapLoaded,
    categoryAvailable,
    currentVersion,
    initializeDashboardTabs,
    items,
    setActiveCategory,
    setCategoryCount,
  }
}
