<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import {
  NButton,
  NForm,
  NFormItem,
  NInput,
  NModal,
  NSelect,
  NTag,
  useDialog,
  useMessage,
} from 'naive-ui'
import { api } from '../api'
import type { ManagedUser } from '../api'
import { useAuth } from '../composables/useAuth'

const message = useMessage()
const dialog = useDialog()
const { state } = useAuth()

const users = ref<ManagedUser[]>([])
const loading = ref(false)

const STATUS_META: Record<string, { label: string; type: 'success' | 'warning' | 'error' | 'default' }> = {
  active: { label: '正常', type: 'success' },
  pending: { label: '待审核', type: 'warning' },
  rejected: { label: '已拒绝', type: 'error' },
  disabled: { label: '已禁用', type: 'default' },
}

const pendingCount = computed(() => users.value.filter((u) => u.status === 'pending').length)

async function load() {
  loading.value = true
  try {
    users.value = await api.listUsers()
  } catch (e) {
    message.error((e as Error).message || '读取用户列表失败')
  } finally {
    loading.value = false
  }
}

onMounted(load)

function fmtDate(v: string | null) {
  if (!v) return '—'
  return new Date(v).toLocaleString('zh-CN', { dateStyle: 'short', timeStyle: 'short' })
}

// ---- 创建用户 ----
const createShow = ref(false)
const createSaving = ref(false)
const createForm = ref({ username: '', password: '', display_name: '', role: 'user' })

function openCreate() {
  createForm.value = { username: '', password: '', display_name: '', role: 'user' }
  createShow.value = true
}

async function submitCreate() {
  const f = createForm.value
  if (f.username.trim().length < 2) {
    message.warning('用户名至少 2 个字符')
    return
  }
  if (f.password.length < 6) {
    message.warning('密码至少 6 位')
    return
  }
  createSaving.value = true
  try {
    await api.createUser({
      username: f.username.trim(),
      password: f.password,
      display_name: f.display_name.trim() || undefined,
      role: f.role,
    })
    message.success('用户已创建')
    createShow.value = false
    await load()
  } catch (e) {
    message.error((e as Error).message || '创建失败')
  } finally {
    createSaving.value = false
  }
}

// ---- 审核拒绝（可填原因） ----
const rejectShow = ref(false)
const rejectTarget = ref<ManagedUser | null>(null)
const rejectReason = ref('')
const rejectSaving = ref(false)

function openReject(u: ManagedUser) {
  rejectTarget.value = u
  rejectReason.value = ''
  rejectShow.value = true
}

async function submitReject() {
  if (!rejectTarget.value) return
  rejectSaving.value = true
  try {
    await api.rejectUser(rejectTarget.value.id, rejectReason.value.trim())
    message.success('已拒绝该注册申请')
    rejectShow.value = false
    await load()
  } catch (e) {
    message.error((e as Error).message || '操作失败')
  } finally {
    rejectSaving.value = false
  }
}

// ---- 其他操作 ----
function withConfirm(content: string, positiveText: string, action: () => Promise<unknown>, done?: string) {
  dialog.warning({
    title: '确认操作',
    content,
    positiveText,
    negativeText: '取消',
    onPositiveClick: async () => {
      try {
        await action()
        if (done) message.success(done)
        await load()
      } catch (e) {
        message.error((e as Error).message || '操作失败')
      }
    },
  })
}

function approve(u: ManagedUser) {
  withConfirm(`确定通过「${u.username}」的注册申请吗？`, '通过', () => api.approveUser(u.id), '已通过审核')
}

function disable(u: ManagedUser) {
  withConfirm(
    `确定禁用「${u.username}」吗？禁用后该用户将立即退出登录且无法再登录，数据保留。`,
    '禁用',
    () => api.disableUser(u.id),
    '已禁用',
  )
}

function enable(u: ManagedUser) {
  withConfirm(`确定启用「${u.username}」吗？`, '启用', () => api.enableUser(u.id), '已启用')
}

function removeUser(u: ManagedUser) {
  const roleNote = u.role === 'admin' ? '该账号是管理员，删除后其管理员权限随之移除。' : ''
  withConfirm(
    `确定删除「${u.username}」吗？${roleNote}该用户的全部数据（岗位、题库、简历、录音等）将被永久删除，不可恢复！`,
    '永久删除',
    () => api.deleteUser(u.id),
    '用户已删除',
  )
}

// ---- 重置密码 ----
const resetShow = ref(false)
const resetTarget = ref<ManagedUser | null>(null)
const resetPassword = ref('')
const resetSaving = ref(false)

function openReset(u: ManagedUser) {
  resetTarget.value = u
  resetPassword.value = ''
  resetShow.value = true
}

async function submitReset() {
  if (!resetTarget.value) return
  if (resetPassword.value.length < 6) {
    message.warning('新密码至少 6 位')
    return
  }
  resetSaving.value = true
  try {
    await api.resetUserPassword(resetTarget.value.id, resetPassword.value)
    message.success('密码已重置，该用户需用新密码重新登录')
    resetShow.value = false
    await load()
  } catch (e) {
    message.error((e as Error).message || '重置失败')
  } finally {
    resetSaving.value = false
  }
}

const isSelf = (u: ManagedUser) => u.id === state.user?.id
// 内置超级管理员账号（admin）：不可删除、不可被他人禁用，且是管理员角色的唯一授予入口
const isBuiltin = (u: ManagedUser) => u.username === 'admin'
const iAmBuiltin = computed(() => state.user?.username === 'admin')

const roleOptions = computed(() =>
  iAmBuiltin.value
    ? [
        { label: '普通用户', value: 'user' },
        { label: '管理员', value: 'admin' },
      ]
    : [{ label: '普通用户', value: 'user' }],
)
</script>

<template>
  <div class="flex h-full flex-col">
    <div class="fade-up flex items-end justify-between gap-3 px-7 pb-4 pt-6 max-md:gap-2.5 max-md:px-4 max-md:pt-4">
      <div>
        <h1 class="text-[21px] font-bold tracking-tight text-zinc-900">
          用户管理
          <n-tag v-if="pendingCount" type="warning" size="small" round class="!ml-1.5 !align-[2px]">
            {{ pendingCount }} 人待审核
          </n-tag>
        </h1>
        <p class="mt-1 text-[13px] text-zinc-400">
          注册审核、账号禁用与删除；删除将清空该用户全部数据，内置 admin 账号不可删除或禁用
        </p>
      </div>
      <n-button type="primary" @click="openCreate">创建用户</n-button>
    </div>

    <div class="min-h-0 flex-1 overflow-y-auto px-7 pb-10 max-md:px-4">
      <div v-if="loading" class="py-16 text-center text-[13px] text-zinc-400">加载中…</div>

      <template v-else>
      <!-- PC 表格 -->
      <div class="hidden overflow-hidden rounded-2xl border border-zinc-100 bg-white md:block">
        <table class="w-full text-left text-[13px]">
          <thead>
            <tr class="border-b border-zinc-100 bg-zinc-50/70 text-[12px] text-zinc-400">
              <th class="px-5 py-3 font-medium">用户</th>
              <th class="px-3 py-3 font-medium">状态</th>
              <th class="px-3 py-3 font-medium">角色</th>
              <th class="px-3 py-3 font-medium">注册时间</th>
              <th class="px-3 py-3 font-medium">最近登录</th>
              <th class="px-5 py-3 text-right font-medium">操作</th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="u in users"
              :key="u.id"
              class="border-b border-zinc-50 transition-colors last:border-0 hover:bg-zinc-50/60"
            >
              <td class="px-5 py-3.5">
                <div class="flex items-center gap-3">
                  <div
                    class="grid h-9 w-9 shrink-0 place-items-center overflow-hidden rounded-full bg-gradient-to-br from-indigo-500 to-violet-500 text-[13px] font-bold text-white"
                  >
                    <img
                      v-if="u.has_avatar"
                      :src="api.userAvatarUrl(u.id)"
                      class="h-full w-full object-cover"
                      alt=""
                    />
                    <template v-else>{{ (u.display_name || u.username).slice(0, 1).toUpperCase() }}</template>
                  </div>
                  <div class="min-w-0">
                    <div class="font-semibold text-zinc-800">
                      {{ u.username }}
                      <span v-if="isSelf(u)" class="ml-1 text-[11px] font-normal text-zinc-400">（我）</span>
                      <span v-if="isBuiltin(u)" class="ml-1 text-[11px] font-normal text-zinc-400">（内置）</span>
                    </div>
                    <div v-if="u.display_name" class="text-[12px] text-zinc-400">{{ u.display_name }}</div>
                    <div v-if="u.status === 'rejected' && u.reject_reason" class="text-[11.5px] text-amber-600">
                      拒绝原因：{{ u.reject_reason }}
                    </div>
                  </div>
                </div>
              </td>
              <td class="px-3 py-3.5">
                <n-tag :type="STATUS_META[u.status]?.type ?? 'default'" size="small" round>
                  {{ STATUS_META[u.status]?.label ?? u.status }}
                </n-tag>
              </td>
              <td class="px-3 py-3.5 text-zinc-600">{{ u.role === 'admin' ? '管理员' : '用户' }}</td>
              <td class="px-3 py-3.5 text-zinc-500">{{ fmtDate(u.created_at) }}</td>
              <td class="px-3 py-3.5 text-zinc-500">{{ fmtDate(u.last_login_at) }}</td>
              <td class="px-5 py-3.5">
                <div class="flex justify-end gap-1.5">
                  <n-button v-if="u.status === 'pending'" size="tiny" type="primary" @click="approve(u)">通过</n-button>
                  <n-button v-if="u.status === 'pending'" size="tiny" type="warning" secondary @click="openReject(u)">拒绝</n-button>
                  <n-button v-if="u.status === 'rejected'" size="tiny" type="primary" secondary @click="approve(u)">改为通过</n-button>
                  <n-button v-if="u.status === 'active' && !isSelf(u) && !isBuiltin(u)" size="tiny" secondary @click="disable(u)">禁用</n-button>
                  <n-button v-if="u.status === 'disabled'" size="tiny" type="primary" secondary @click="enable(u)">启用</n-button>
                  <n-button v-if="!isSelf(u) && (u.role !== 'admin' || iAmBuiltin)" size="tiny" secondary @click="openReset(u)">重置密码</n-button>
                  <n-button v-if="!isSelf(u) && !isBuiltin(u)" size="tiny" type="error" secondary @click="removeUser(u)">删除</n-button>
                </div>
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      <!-- 移动端卡片 -->
      <div class="flex flex-col gap-2.5 md:hidden">
        <div
          v-for="u in users"
          :key="u.id"
          class="rounded-xl border border-zinc-100 bg-white p-3.5"
        >
          <div class="flex items-center gap-3">
            <div
              class="grid h-9 w-9 shrink-0 place-items-center overflow-hidden rounded-full bg-gradient-to-br from-indigo-500 to-violet-500 text-[13px] font-bold text-white"
            >
              <img v-if="u.has_avatar" :src="api.userAvatarUrl(u.id)" class="h-full w-full object-cover" alt="" />
              <template v-else>{{ (u.display_name || u.username).slice(0, 1).toUpperCase() }}</template>
            </div>
            <div class="min-w-0 flex-1">
              <div class="truncate text-[14px] font-semibold text-zinc-800">
                {{ u.username }}
                <span v-if="isSelf(u)" class="ml-1 text-[11px] font-normal text-zinc-400">（我）</span>
                <span v-if="isBuiltin(u)" class="ml-1 text-[11px] font-normal text-zinc-400">（内置）</span>
              </div>
              <div class="mt-0.5 flex items-center gap-1.5 text-[11.5px] text-zinc-400">
                <n-tag :type="STATUS_META[u.status]?.type ?? 'default'" size="small" round>
                  {{ STATUS_META[u.status]?.label ?? u.status }}
                </n-tag>
                {{ u.role === 'admin' ? '管理员' : '用户' }}
              </div>
            </div>
          </div>
          <div v-if="u.status === 'rejected' && u.reject_reason" class="mt-2 text-[11.5px] text-amber-600">
            拒绝原因：{{ u.reject_reason }}
          </div>
          <div class="mt-2 text-[11.5px] text-zinc-400">注册 {{ fmtDate(u.created_at) }} · 最近登录 {{ fmtDate(u.last_login_at) }}</div>
          <div class="mt-2.5 flex flex-wrap gap-1.5">
            <n-button v-if="u.status === 'pending'" size="tiny" type="primary" @click="approve(u)">通过</n-button>
            <n-button v-if="u.status === 'pending'" size="tiny" type="warning" secondary @click="openReject(u)">拒绝</n-button>
            <n-button v-if="u.status === 'rejected'" size="tiny" type="primary" secondary @click="approve(u)">改为通过</n-button>
            <n-button v-if="u.status === 'active' && !isSelf(u) && !isBuiltin(u)" size="tiny" secondary @click="disable(u)">禁用</n-button>
            <n-button v-if="u.status === 'disabled'" size="tiny" type="primary" secondary @click="enable(u)">启用</n-button>
            <n-button v-if="!isSelf(u) && (u.role !== 'admin' || iAmBuiltin)" size="tiny" secondary @click="openReset(u)">重置密码</n-button>
            <n-button v-if="!isSelf(u) && !isBuiltin(u)" size="tiny" type="error" secondary @click="removeUser(u)">删除</n-button>
          </div>
        </div>
      </div>
      </template>
    </div>

    <!-- 创建用户弹窗 -->
    <n-modal v-model:show="createShow" preset="card" title="创建用户" class="!w-[400px] !max-w-[calc(100vw-16px)]">
      <n-form label-placement="top" size="small" :show-require-mark="false">
        <n-form-item label="用户名">
          <n-input v-model:value="createForm.username" placeholder="2-32 个字符" />
        </n-form-item>
        <n-form-item label="昵称（可选）">
          <n-input v-model:value="createForm.display_name" placeholder="展示用昵称" />
        </n-form-item>
        <n-form-item label="初始密码">
          <n-input v-model:value="createForm.password" type="password" show-password-on="click" placeholder="至少 6 位" />
        </n-form-item>
        <n-form-item label="角色">
          <n-select v-model:value="createForm.role" :options="roleOptions" />
        </n-form-item>
        <div class="flex justify-end gap-2">
          <n-button quaternary @click="createShow = false">取消</n-button>
          <n-button type="primary" :loading="createSaving" @click="submitCreate">创建</n-button>
        </div>
      </n-form>
    </n-modal>

    <!-- 拒绝原因弹窗 -->
    <n-modal v-model:show="rejectShow" preset="card" title="拒绝注册申请" class="!w-[400px] !max-w-[calc(100vw-16px)]">
      <p class="mb-3 text-[12.5px] text-zinc-500">
        拒绝「{{ rejectTarget?.username }}」的注册申请，原因（可选）会通知给对方：
      </p>
      <n-input
        v-model:value="rejectReason"
        type="textarea"
        :rows="3"
        placeholder="如：用户名不符合规范，请使用真实姓名重新申请"
      />
      <div class="mt-4 flex justify-end gap-2">
        <n-button quaternary @click="rejectShow = false">取消</n-button>
        <n-button type="warning" :loading="rejectSaving" @click="submitReject">拒绝</n-button>
      </div>
    </n-modal>

    <!-- 重置密码弹窗 -->
    <n-modal v-model:show="resetShow" preset="card" title="重置密码" class="!w-[400px] !max-w-[calc(100vw-16px)]">
      <p class="mb-3 text-[12.5px] text-zinc-500">
        为「{{ resetTarget?.username }}」设置新密码，重置后该用户的所有登录会话将立即失效：
      </p>
      <n-input v-model:value="resetPassword" type="password" show-password-on="click" placeholder="新密码（至少 6 位）" />
      <div class="mt-4 flex justify-end gap-2">
        <n-button quaternary @click="resetShow = false">取消</n-button>
        <n-button type="primary" :loading="resetSaving" @click="submitReset">重置</n-button>
      </div>
    </n-modal>
  </div>
</template>
