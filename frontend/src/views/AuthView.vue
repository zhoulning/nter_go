<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { NButton, NForm, NFormItem, NInput, NTabPane, NTabs, useMessage } from 'naive-ui'
import { FlashOutline } from '@vicons/ionicons5'
import { api } from '../api'
import { useAuth } from '../composables/useAuth'

const message = useMessage()
const { login, register } = useAuth()

const mode = ref<'login' | 'register'>('login')
const submitted = ref(false) // 注册提交成功 → 待审核提示页
const regEnabled = ref(true)
const loading = ref(false)

const loginForm = ref({ username: '', password: '' })
const regForm = ref({ username: '', password: '', confirm: '', display_name: '' })

onMounted(async () => {
  try {
    regEnabled.value = (await api.registerStatus()).enabled
  } catch {
    regEnabled.value = true
  }
})

async function submitLogin() {
  if (!loginForm.value.username.trim() || !loginForm.value.password) {
    message.warning('请输入用户名和密码')
    return
  }
  loading.value = true
  try {
    await login(loginForm.value.username.trim(), loginForm.value.password)
    message.success('欢迎回来')
  } catch (e) {
    message.error((e as Error).message || '登录失败')
  } finally {
    loading.value = false
  }
}

async function submitRegister() {
  const f = regForm.value
  if (f.username.trim().length < 2) {
    message.warning('用户名至少 2 个字符')
    return
  }
  if (f.password.length < 6) {
    message.warning('密码至少 6 位')
    return
  }
  if (f.password !== f.confirm) {
    message.warning('两次输入的密码不一致')
    return
  }
  loading.value = true
  try {
    const res = await register(f.username.trim(), f.password, f.display_name.trim())
    submitted.value = true
    message.success(res.message)
  } catch (e) {
    message.error((e as Error).message || '注册失败')
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div
    class="grid min-h-dvh place-items-center bg-gradient-to-br from-indigo-50 via-white to-violet-50 px-4 py-10"
  >
    <div class="w-full max-w-[400px]">
      <!-- 品牌区 -->
      <div class="mb-7 flex flex-col items-center">
        <div
          class="grid h-14 w-14 place-items-center rounded-2xl bg-gradient-to-br from-indigo-500 to-violet-500 text-white shadow-[0_8px_24px_rgba(99,102,241,0.45)]"
        >
          <n-icon :component="FlashOutline" :size="30" />
        </div>
        <h1 class="mt-3.5 text-[22px] font-bold tracking-tight text-zinc-900">进击の面试</h1>
        <p class="mt-1 text-[12.5px] text-zinc-400">面试跟踪管理</p>
      </div>

      <div class="rounded-2xl border border-zinc-100 bg-white p-6 shadow-[0_12px_40px_-12px_rgba(16,24,40,0.12)] max-md:p-5">
        <!-- 注册提交后的待审核提示 -->
        <template v-if="submitted">
          <div class="py-4 text-center">
            <div
              class="mx-auto grid h-12 w-12 place-items-center rounded-full bg-amber-50 text-[22px]"
            >
              ⏳
            </div>
            <h2 class="mt-3 text-[16px] font-bold text-zinc-900">注册已提交</h2>
            <p class="mx-auto mt-2 max-w-[280px] text-[13px] leading-relaxed text-zinc-500">
              账号正在等待管理员审核，审核通过后即可登录使用。
            </p>
            <n-button class="mt-5" @click="submitted = false; mode = 'login'">返回登录</n-button>
          </div>
        </template>

        <template v-else>
          <n-tabs v-model:value="mode" type="segment" size="small" animated>
            <n-tab-pane name="login" tab="登录">
              <n-form label-placement="top" size="medium" class="pt-4" :show-require-mark="false">
                <n-form-item label="用户名">
                  <n-input
                    v-model:value="loginForm.username"
                    placeholder="用户名"
                    @keyup.enter="submitLogin"
                  />
                </n-form-item>
                <n-form-item label="密码">
                  <n-input
                    v-model:value="loginForm.password"
                    type="password"
                    show-password-on="click"
                    placeholder="密码"
                    @keyup.enter="submitLogin"
                  />
                </n-form-item>
                <n-button
                  type="primary"
                  block
                  class="!mt-1"
                  :loading="loading"
                  @click="submitLogin"
                >
                  登 录
                </n-button>
              </n-form>
            </n-tab-pane>

            <n-tab-pane name="register" :tab="regEnabled ? '注册' : '注册（未开放）'" :disabled="!regEnabled">
              <n-form label-placement="top" size="medium" class="pt-4" :show-require-mark="false">
                <n-form-item label="用户名">
                  <n-input v-model:value="regForm.username" placeholder="2-32 个字符" />
                </n-form-item>
                <n-form-item label="昵称（可选）">
                  <n-input v-model:value="regForm.display_name" placeholder="展示用昵称" />
                </n-form-item>
                <n-form-item label="密码">
                  <n-input
                    v-model:value="regForm.password"
                    type="password"
                    show-password-on="click"
                    placeholder="至少 6 位"
                  />
                </n-form-item>
                <n-form-item label="确认密码">
                  <n-input
                    v-model:value="regForm.confirm"
                    type="password"
                    show-password-on="click"
                    placeholder="再输入一次"
                    @keyup.enter="submitRegister"
                  />
                </n-form-item>
                <n-button
                  type="primary"
                  block
                  class="!mt-1"
                  :loading="loading"
                  @click="submitRegister"
                >
                  提交注册
                </n-button>
                <p class="mt-3 text-center text-[11.5px] leading-relaxed text-zinc-400">
                  注册后需管理员审核通过才能登录
                </p>
              </n-form>
            </n-tab-pane>
          </n-tabs>
        </template>
      </div>
    </div>
  </div>
</template>
