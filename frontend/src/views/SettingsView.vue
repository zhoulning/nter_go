<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { NButton, NForm, NFormItem, NInput, NSwitch, NTabPane, NTabs, NUpload, useDialog, useMessage } from 'naive-ui'
import type { UploadFileInfo, UploadInst } from 'naive-ui'
import { api } from '../api'
import type { AiSettingsInfo, AuthUser, KnowledgeBaseInfo } from '../api'
import { setAuthUser, useAuth, isBuiltinAdmin } from '../composables/useAuth'

const message = useMessage()
const dialog = useDialog()
const { state } = useAuth()

const activeTab = ref('profile')
const savingProfile = ref(false)
const savingPassword = ref(false)

// ---- 个人设置 ----
const displayName = ref('')
const avatarUrl = ref<string | null>(null)
const avatarUploadRef = ref<UploadInst | null>(null)
const passwordForm = ref({ old_password: '', new_password: '', confirm: '' })

function applyUser(u: AuthUser) {
  displayName.value = u.display_name ?? ''
  avatarUrl.value = u.avatar_url ? `${u.avatar_url}?t=${Date.now()}` : null
}

onMounted(() => {
  if (state.user) applyUser(state.user)
})

async function onAvatarChange(options: { file: UploadFileInfo }) {
  const f = options.file.file
  if (!f) return
  try {
    const user = await api.uploadAvatar(f)
    setAuthUser(user)
    applyUser(user)
    message.success('头像已更新')
  } catch (e) {
    message.error((e as Error).message || '头像上传失败')
  } finally {
    // 清空 n-upload 内部文件列表：max=1 时不清会导致触发按钮永久禁用
    avatarUploadRef.value?.clear()
  }
}

function onAvatarRemove() {
  dialog.warning({
    title: '移除头像',
    content: '确定要移除当前头像吗？',
    positiveText: '移除',
    negativeText: '取消',
    onPositiveClick: async () => {
      try {
        const user = await api.deleteAvatar()
        setAuthUser(user)
        applyUser(user)
      } catch (e) {
        message.error((e as Error).message || '移除失败')
      }
    },
  })
}

async function saveProfile() {
  savingProfile.value = true
  try {
    const user = await api.updateProfile({ display_name: displayName.value.trim() || undefined })
    setAuthUser(user)
    message.success('个人资料已保存')
  } catch (e) {
    message.error((e as Error).message || '保存失败')
  } finally {
    savingProfile.value = false
  }
}

async function savePassword() {
  const f = passwordForm.value
  if (!f.old_password || !f.new_password) {
    message.warning('请填写当前密码和新密码')
    return
  }
  if (f.new_password.length < 6) {
    message.warning('新密码至少 6 位')
    return
  }
  if (f.new_password !== f.confirm) {
    message.warning('两次输入的新密码不一致')
    return
  }
  savingPassword.value = true
  try {
    await api.updatePassword({ old_password: f.old_password, new_password: f.new_password })
    passwordForm.value = { old_password: '', new_password: '', confirm: '' }
    message.success('密码已修改')
  } catch (e) {
    message.error((e as Error).message || '修改失败')
  } finally {
    savingPassword.value = false
  }
}

// ---- 系统配置（仅管理员） ----
const loadingSys = ref(false)
const savingSys = ref(false)
const aiForm = ref({ base_url: 'https://open.bigmodel.cn/api/paas/v4', model: 'glm-4-flash', api_key: '' })
const aiInfo = ref<AiSettingsInfo | null>(null)
const browserCdp = ref('http://127.0.0.1:9222')
const kbPath = ref('')
const kbInfo = ref<KnowledgeBaseInfo | null>(null)
const regEnabled = ref(true)

async function loadSysSettings() {
  if (!isBuiltinAdmin.value) return
  loadingSys.value = true
  try {
    aiInfo.value = await api.getAiSettings()
    aiForm.value.base_url = aiInfo.value.base_url
    aiForm.value.model = aiInfo.value.model
    aiForm.value.api_key = ''
    browserCdp.value = (await api.getBrowserSettings()).cdp_endpoint
    kbInfo.value = await api.getKbSettings()
    kbPath.value = kbInfo.value.path
    regEnabled.value = (await api.getRegistrationSettings()).enabled
  } catch (e) {
    message.error((e as Error).message || '读取设置失败')
  } finally {
    loadingSys.value = false
  }
}

onMounted(loadSysSettings)

async function saveAi() {
  savingSys.value = true
  try {
    const payload: { base_url?: string; model?: string; api_key?: string } = {
      base_url: aiForm.value.base_url.trim(),
      model: aiForm.value.model.trim(),
    }
    if (aiForm.value.api_key.trim()) payload.api_key = aiForm.value.api_key.trim()
    aiInfo.value = await api.saveAiSettings(payload)
    aiForm.value.api_key = ''
    message.success('AI 配置已保存')
  } catch (e) {
    message.error((e as Error).message || '保存失败')
  } finally {
    savingSys.value = false
  }
}

async function saveBrowser() {
  savingSys.value = true
  try {
    browserCdp.value = (await api.saveBrowserSettings({ cdp_endpoint: browserCdp.value.trim() })).cdp_endpoint
    message.success('浏览器配置已保存')
  } catch (e) {
    message.error((e as Error).message || '保存失败')
  } finally {
    savingSys.value = false
  }
}

async function saveKb() {
  savingSys.value = true
  try {
    kbInfo.value = await api.saveKbSettings({ path: kbPath.value.trim() })
    message.success('知识库配置已保存')
  } catch (e) {
    message.error((e as Error).message || '保存失败')
  } finally {
    savingSys.value = false
  }
}

async function toggleRegistration(enabled: boolean) {
  try {
    regEnabled.value = (await api.saveRegistrationSettings(enabled)).enabled
    message.success(enabled ? '已开放注册' : '已关闭注册')
  } catch (e) {
    regEnabled.value = !enabled
    message.error((e as Error).message || '保存失败')
  }
}
</script>

<template>
  <div class="h-full overflow-y-auto">
    <div class="fade-up flex items-end justify-between px-7 pb-4 pt-6 max-md:px-4 max-md:pt-4">
      <div>
        <h1 class="text-[21px] font-bold tracking-tight text-zinc-900">系统设置</h1>
        <p class="mt-1 text-[13px] text-zinc-400">个人资料与系统配置</p>
      </div>
    </div>

    <div class="fade-up px-7 pb-10 max-md:px-4">
      <div class="rounded-2xl border border-zinc-100 bg-white p-6 max-md:p-4">
        <n-tabs v-model:value="activeTab" type="line" animated>
          <!-- 个人设置：所有用户 -->
          <n-tab-pane name="profile" tab="个人设置">
            <div class="flex items-center gap-5 max-md:flex-col max-md:items-start">
              <div class="flex flex-col items-center gap-2">
                <div
                  class="grid h-[72px] w-[72px] place-items-center overflow-hidden rounded-full bg-gradient-to-br from-indigo-500 to-violet-500 text-[26px] font-bold text-white"
                >
                  <img
                    v-if="avatarUrl"
                    :src="avatarUrl"
                    class="h-full w-full object-cover"
                    alt="头像"
                  />
                  <template v-else>{{ (displayName || state.user?.username || '?').slice(0, 1).toUpperCase() }}</template>
                </div>
                <n-upload
                  ref="avatarUploadRef"
                  :max="1"
                  :default-upload="false"
                  accept=".png,.jpg,.jpeg,.webp,.gif"
                  :show-file-list="false"
                  @change="onAvatarChange"
                >
                  <n-button size="tiny" quaternary type="primary">更换头像</n-button>
                </n-upload>
                <n-button
                  v-if="avatarUrl"
                  size="tiny"
                  quaternary
                  type="error"
                  @click="onAvatarRemove"
                >
                  移除
                </n-button>
              </div>

              <div class="min-w-0 flex-1 max-w-[560px]">
                <n-form label-placement="top" size="small" :show-require-mark="false">
                  <n-form-item label="用户名">
                    <n-input :value="state.user?.username ?? ''" disabled />
                  </n-form-item>
                  <n-form-item label="昵称">
                    <n-input
                      v-model:value="displayName"
                      placeholder="展示用昵称（留空则显示用户名）"
                      @keyup.enter="saveProfile"
                    />
                  </n-form-item>
                  <n-button type="primary" size="small" :loading="savingProfile" @click="saveProfile">
                    保存资料
                  </n-button>
                </n-form>
              </div>
            </div>

            <div class="mt-7 border-t border-zinc-100 pt-5">
              <div class="mb-3 text-[13px] font-semibold text-zinc-800">修改密码</div>
              <n-form label-placement="top" size="small" :show-require-mark="false" class="max-w-[360px]">
                <n-form-item label="当前密码">
                  <n-input v-model:value="passwordForm.old_password" type="password" show-password-on="click" placeholder="当前密码" />
                </n-form-item>
                <n-form-item label="新密码">
                  <n-input v-model:value="passwordForm.new_password" type="password" show-password-on="click" placeholder="至少 6 位" />
                </n-form-item>
                <n-form-item label="确认新密码">
                  <n-input v-model:value="passwordForm.confirm" type="password" show-password-on="click" placeholder="再输入一次" />
                </n-form-item>
                <n-button type="primary" size="small" :loading="savingPassword" @click="savePassword">
                  修改密码
                </n-button>
              </n-form>
            </div>
          </n-tab-pane>

          <!-- 以下仅内置管理员账号（admin）可见 -->
          <template v-if="isBuiltinAdmin">
            <n-tab-pane name="ai" tab="AI 配置">
              <n-form label-placement="top" size="small" :show-require-mark="false" class="max-w-[640px]">
                <n-form-item label="API Base URL">
                  <n-input v-model:value="aiForm.base_url" placeholder="https://open.bigmodel.cn/api/paas/v4" />
                </n-form-item>
                <n-form-item label="模型">
                  <n-input v-model:value="aiForm.model" placeholder="如：glm-4-flash" />
                </n-form-item>
                <n-form-item label="API Key">
                  <n-input
                    v-model:value="aiForm.api_key"
                    type="password"
                    show-password-on="click"
                    :placeholder="aiInfo?.api_key_configured
                      ? `已配置（${aiInfo.api_key_masked}），留空则不修改`
                      : '粘贴 API Key'"
                  />
                </n-form-item>
                <n-button type="primary" size="small" :loading="savingSys" @click="saveAi">保存</n-button>
              </n-form>
              <div class="mt-4 rounded-lg bg-zinc-50 px-3 py-2.5 text-[11.5px] leading-relaxed text-zinc-500">
                全局配置，对所有用户生效；自动识别 OpenAI / Anthropic 协议。常用配置：<br />
                · 智谱国内 <code class="text-zinc-700">https://open.bigmodel.cn/api/paas/v4</code>（模型如 <code class="text-zinc-700">glm-4-flash</code>）<br />
                · 智谱国际 <code class="text-zinc-700">https://api.z.ai/api/anthropic</code><br />
                · DeepSeek <code class="text-zinc-700">https://api.deepseek.com/v1</code>（模型 <code class="text-zinc-700">deepseek-chat</code>）
              </div>
            </n-tab-pane>

            <n-tab-pane name="browser" tab="浏览器直连">
              <n-form label-placement="top" size="small" :show-require-mark="false" class="max-w-[640px]">
                <n-form-item label="调试端口地址（提取 BOSS直聘链接用）" :show-feedback="false">
                  <n-input v-model:value="browserCdp" placeholder="http://127.0.0.1:9222" />
                </n-form-item>
                <n-button type="primary" size="small" class="!mt-3" :loading="savingSys" @click="saveBrowser">
                  保存
                </n-button>
              </n-form>
              <div class="mt-4 rounded-lg bg-amber-50/70 px-3 py-2.5 text-[11.5px] leading-relaxed text-zinc-500">
                使用项目根目录的 <code class="text-zinc-700">start-boss-browser.bat</code>
                启动专用浏览器（独立配置，不影响日常 Chrome），在其中登录 BOSS 直聘一次即可长期有效。
              </div>
            </n-tab-pane>

            <n-tab-pane name="kb" tab="知识库">
              <n-form label-placement="top" size="small" :show-require-mark="false" class="max-w-[640px]">
                <n-form-item label="Obsidian 知识库文件夹路径" :show-feedback="false">
                  <n-input v-model:value="kbPath" placeholder="如 D:\Notes\MyVault（Obsidian 仓库文件夹）" />
                </n-form-item>
                <n-button type="primary" size="small" class="!mt-3" :loading="savingSys" @click="saveKb">
                  保存
                </n-button>
              </n-form>
              <div class="mt-4 rounded-lg bg-zinc-50 px-3 py-2.5 text-[11.5px] leading-relaxed text-zinc-500">
                题库 AI 答案与模拟面试复盘生成时会按题目关键词检索相关笔记片段作为参考。
                <span class="font-medium text-zinc-700">知识库严格只读——应用只检索读取，绝不写入、修改或删除其中任何文件</span>。
                支持 .md / .txt / .pdf / .docx，自动跳过 <code class="text-zinc-700">.obsidian</code> 配置目录；留空则不启用。
                <template v-if="kbInfo && kbInfo.path">
                  <br />
                  <span :class="kbInfo.exists ? 'text-emerald-600' : 'text-amber-600'">
                    {{ kbInfo.exists ? `已识别 ${kbInfo.file_count} 篇笔记 / 文档` : '当前路径不存在，请检查' }}
                  </span>
                </template>
              </div>
            </n-tab-pane>

            <n-tab-pane name="registration" tab="注册">
              <div class="flex max-w-[640px] items-center justify-between gap-4 rounded-lg bg-zinc-50 px-4 py-3">
                <div>
                  <div class="text-[13px] font-semibold text-zinc-800">开放自主注册</div>
                  <p class="mt-0.5 text-[11.5px] leading-relaxed text-zinc-500">
                    关闭后登录页不再提供注册入口，只能由管理员在「用户管理」中直接创建账号。
                  </p>
                </div>
                <n-switch :value="regEnabled" size="large" @update:value="toggleRegistration" />
              </div>
            </n-tab-pane>
          </template>
        </n-tabs>
      </div>
    </div>
  </div>
</template>
