<script setup>
import { computed } from 'vue'

const props = defineProps({
  config: {
    type: Object,
    required: true,
  },
})

const appearanceGroup = Object.freeze({
  slug: 'appearance',
  name: '界面主题',
  icon: '主题',
  summary: '选择浅色或深色主题，以及圆角或直角界面。',
  item_count: 2,
})

const groups = computed(() => {
  const entries = Array.isArray(props.config.groups) ? [...props.config.groups] : []
  if (entries.some(group => group.slug === appearanceGroup.slug)) return entries
  const aboutIndex = entries.findIndex(group => group.slug === 'about')
  entries.splice(aboutIndex < 0 ? entries.length : aboutIndex, 0, appearanceGroup)
  return entries
})
const itemCount = computed(() => Array.isArray(props.config.items) ? props.config.items.length : 0)
</script>

<template>
  <div class="settings-index">
    <div class="settings-overview">
      <div class="settings-overview-copy">
        <h2>业务配置</h2>
      </div>
      <div class="settings-overview-stats">
        <div class="settings-stat">
          <span class="settings-stat-value">{{ groups.length }}</span>
          <span class="settings-stat-label">分组</span>
        </div>
        <div class="settings-stat">
          <span class="settings-stat-value">{{ itemCount }}</span>
          <span class="settings-stat-label">配置项</span>
        </div>
      </div>
    </div>
    <nav class="settings-grid" aria-label="设置分组">
      <RouterLink
        v-for="group in groups"
        :key="group.slug"
        class="settings-card"
        :to="`/admin/settings/${group.slug}`"
        :aria-label="`进入${group.name}设置`"
      >
        <span class="settings-card-icon" aria-hidden="true">{{ group.icon || '设置' }}</span>
        <span class="settings-card-copy">
          <span class="settings-card-title">{{ group.name }}</span>
          <span class="settings-card-summary">{{ group.summary || '维护该分组的业务配置。' }}</span>
          <span class="settings-card-meta">{{ Number(group.item_count || 0) }} 项设置</span>
        </span>
        <span class="settings-card-arrow" aria-hidden="true">›</span>
      </RouterLink>
    </nav>
  </div>
</template>
