<script setup>
import { computed } from 'vue'
import { useTheme } from '../composables/useTheme.js'

const { cornerStyle, setCornerStyle, setTheme, theme } = useTheme()

const colorOptions = [
  { value: 'light', label: '浅色', description: '适合明亮环境与日间查看' },
  { value: 'dark', label: '深色', description: '适合低光环境与长时间盯盘' },
]
const cornerOptions = [
  { value: 'rounded', label: '圆角', description: '柔和的卡片与控件边缘' },
  { value: 'square', label: '直角', description: '紧凑严肃的金融终端风格' },
]

const appearanceSummary = computed(() => (
  `${theme.value === 'dark' ? '深色' : '浅色'} · ${cornerStyle.value === 'rounded' ? '圆角' : '直角'}`
))
</script>

<template>
  <div class="settings-detail appearance-settings-page">
    <nav class="settings-breadcrumbs" aria-label="设置导航">
      <RouterLink class="settings-back-link" to="/admin">
        <span aria-hidden="true">←</span><span>全部设置</span>
      </RouterLink>
    </nav>
    <section class="settings-group appearance-settings-panel" aria-labelledby="appearanceSettingsTitle">
      <div class="settings-group-head appearance-settings-head">
        <div>
          <h2 id="appearanceSettingsTitle">界面主题</h2>
          <p class="settings-group-note">外观偏好即时生效，并保存在当前浏览器。</p>
        </div>
        <span class="appearance-current" aria-live="polite">{{ appearanceSummary }}</span>
      </div>
      <div class="appearance-settings-body">
        <div class="appearance-settings-grid">
          <fieldset class="appearance-option-group">
            <legend>主题颜色</legend>
            <label
              v-for="option in colorOptions"
              :key="option.value"
              class="appearance-option-card"
              :class="{ selected: theme === option.value }"
            >
              <input
                class="appearance-option-input"
                type="radio"
                name="appearance-color"
                :value="option.value"
                :checked="theme === option.value"
                @change="setTheme(option.value)"
              />
              <span class="appearance-color-sample" :class="option.value" aria-hidden="true">
                <i /><i />
              </span>
              <span class="appearance-option-copy">
                <strong>{{ option.label }}</strong>
                <small>{{ option.description }}</small>
              </span>
              <span class="appearance-option-check" aria-hidden="true">✓</span>
            </label>
          </fieldset>
          <fieldset class="appearance-option-group">
            <legend>边角样式</legend>
            <label
              v-for="option in cornerOptions"
              :key="option.value"
              class="appearance-option-card"
              :class="{ selected: cornerStyle === option.value }"
            >
              <input
                class="appearance-option-input"
                type="radio"
                name="appearance-corners"
                :value="option.value"
                :checked="cornerStyle === option.value"
                @change="setCornerStyle(option.value)"
              />
              <span class="appearance-corner-sample" :class="option.value" aria-hidden="true"><i /></span>
              <span class="appearance-option-copy">
                <strong>{{ option.label }}</strong>
                <small>{{ option.description }}</small>
              </span>
              <span class="appearance-option-check" aria-hidden="true">✓</span>
            </label>
          </fieldset>
        </div>
      </div>
    </section>
  </div>
</template>
