<script setup lang="ts">
import { ref, watch } from 'vue'
import { NButton, NForm, NFormItem, NInput, NModal, useMessage } from 'naive-ui'
import { api } from '../api'
import type { AiSettingsInfo } from '../api'

const props = defineProps<{ show: boolean }>()
const emit = defineEmits<{ (e: 'update:show', v: boolean): void }>()

const message = useMessage()
const saving = ref(false)
const loading = ref(false)

const form = ref({
  base_url: 'https://open.bigmodel.cn/api/paas/v4',
  model: 'glm-4-flash',
  api_key: '',
})
const browserCdp = ref('http://127.0.0.1:9222')
const configuredInfo = ref<AiSettingsInfo | null>(null)

watch(
  () => props.show,
  async (v) => {
    if (!v) return
    loading.value = true
    try {
      const info = await api.getAiSettings()
      configuredInfo.value = info
      form.value.base_url = info.base_url
      form.value.model = info.model
      form.value.api_key = ''
      const browser = await api.getBrowserSettings()
      browserCdp.value = browser.cdp_endpoint
    } catch (e) {
      message.error((e as Error).message || '读取设置失败')
    } finally {
      loading.value = false
    }
  },
)

async function save() {
  saving.value = true
  try {
    const payload: { base_url?: string; model?: string; api_key?: string } = {
      base_url: form.value.base_url.trim(),
      model: form.value.model.trim(),
    }
    if (form.value.api_key.trim()) payload.api_key = form.value.api_key.trim()
    const info = await api.saveAiSettings(payload)
    configuredInfo.value = info
    form.value.api_key = ''
    await api.saveBrowserSettings({ cdp_endpoint: browserCdp.value.trim() })
    message.success('设置已保存')
    emit('update:show', false)
  } catch (e) {
    message.error((e as Error).message || '保存失败')
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <n-modal :show="show" transform-origin="center" @update:show="emit('update:show', $event)">
    <div class="modal-card">
      <div class="mb-5">
        <h2 class="text-[16px] font-bold text-zinc-900">AI 设置</h2>
        <p class="mt-0.5 text-[12px] text-zinc-400">
          配置大模型后可使用「新增岗位 · AI 提取」等功能；Key 仅保存在本机 SQLite
        </p>
      </div>

      <n-form label-placement="top" size="small" :show-require-mark="false">
        <n-form-item label="API Base URL">
          <n-input v-model:value="form.base_url" placeholder="https://open.bigmodel.cn/api/paas/v4" />
        </n-form-item>
        <n-form-item label="模型">
          <n-input v-model:value="form.model" placeholder="如：glm-4-flash" />
        </n-form-item>
        <n-form-item label="API Key">
          <n-input
            v-model:value="form.api_key"
            type="password"
            show-password-on="click"
            :placeholder="configuredInfo?.api_key_configured
              ? `已配置（${configuredInfo.api_key_masked}），留空则不修改`
              : '粘贴智谱 API Key'"
          />
        </n-form-item>
      </n-form>

      <div class="mb-4 rounded-lg bg-zinc-50 px-3 py-2.5 text-[11.5px] leading-relaxed text-zinc-500">
        自动识别 OpenAI / Anthropic 协议。常用配置：<br />
        · 智谱国内
        <code class="text-zinc-700">https://open.bigmodel.cn/api/paas/v4</code>（模型如
        <code class="text-zinc-700">glm-4-flash</code>）<br />
        · 智谱国际
        <code class="text-zinc-700">https://api.z.ai/api/anthropic</code><br />
        · DeepSeek
        <code class="text-zinc-700">https://api.deepseek.com/v1</code>（模型
        <code class="text-zinc-700">deepseek-chat</code>）
      </div>

      <div class="mb-4 border-t border-zinc-100 pt-4">
        <div class="mb-2 text-[13px] font-semibold text-zinc-800">浏览器直连（提取 BOSS直聘链接用）</div>
        <n-form-item label="调试端口地址" :show-feedback="false">
          <n-input v-model:value="browserCdp" placeholder="http://127.0.0.1:9222" />
        </n-form-item>
        <div class="mt-2 rounded-lg bg-amber-50/70 px-3 py-2.5 text-[11.5px] leading-relaxed text-zinc-500">
          使用项目根目录的 <code class="text-zinc-700">start-boss-browser.bat</code>
          启动专用浏览器（独立配置，不影响日常 Chrome），在其中登录 BOSS 直聘一次即可长期有效。
          提取时应用会自动连上它读取页面。
        </div>
      </div>

      <div class="flex justify-end gap-2.5">
        <n-button quaternary @click="emit('update:show', false)">取消</n-button>
        <n-button type="primary" class="!px-5" :loading="saving" @click="save">保存</n-button>
      </div>
    </div>
  </n-modal>
</template>

<style scoped>
.modal-card {
  width: 480px;
  max-width: calc(100vw - 48px);
  background: #fff;
  border-radius: 16px;
  padding: 24px;
  box-shadow:
    0 20px 50px -12px rgba(16, 24, 40, 0.25),
    0 0 0 1px rgba(16, 24, 40, 0.04);
}
</style>
