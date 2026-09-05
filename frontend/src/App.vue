<script setup lang="ts">
import { computed, onMounted } from 'vue'
import { NConfigProvider, NDialogProvider, NMessageProvider, dateZhCN, zhCN } from 'naive-ui'
import type { GlobalThemeOverrides } from 'naive-ui'
import AppShell from './components/AppShell.vue'
import AuthView from './views/AuthView.vue'
import { useAuth } from './composables/useAuth'

const { state, fetchMe } = useAuth()
onMounted(fetchMe)

const FONT_FAMILY =
  "Inter, 'Noto Sans SC', -apple-system, 'Segoe UI', 'PingFang SC', 'Microsoft YaHei', sans-serif"

const themeOverrides = computed<GlobalThemeOverrides>(() => ({
  common: {
    primaryColor: '#6366f1',
    primaryColorHover: '#818cf8',
    primaryColorPressed: '#4f46e5',
    primaryColorSuppl: '#6366f1',
    borderRadius: '8px',
    fontFamily: FONT_FAMILY,
  },
}))
</script>

<template>
  <n-config-provider :theme-overrides="themeOverrides" :locale="zhCN" :date-locale="dateZhCN">
    <n-message-provider>
      <n-dialog-provider>
        <!-- 登录门卫：登录态检查中 → 空白；未登录 → 登录/注册页；已登录 → 应用壳 -->
        <div v-if="!state.ready" class="grid min-h-dvh place-items-center bg-white">
          <div class="text-[13px] text-zinc-400">加载中…</div>
        </div>
        <AuthView v-else-if="!state.user" />
        <AppShell v-else />
      </n-dialog-provider>
    </n-message-provider>
  </n-config-provider>
</template>
