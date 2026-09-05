<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import {
  NAlert,
  NButton,
  NDynamicTags,
  NFormItem,
  NInput,
  NInputNumber,
  NSelect,
  NTabPane,
  NTabs,
  NTag,
  useMessage,
} from 'naive-ui'
import { api } from '../api'
import { EMPTY_PROFILE } from '../types'
import type { CareerProfile, Resume, TrackProfile } from '../types'
import { isAdmin, isBuiltinAdmin } from '../composables/useAuth'

const message = useMessage()

const activeTab = ref('profile')
const loading = ref(false)
const saving = ref(false)
const generating = ref(false)
const switching = ref('')

const tracks = ref<TrackProfile[]>([])
const currentKey = ref('')
const resumes = ref<Resume[]>([])
const genResumeId = ref<number | null>(null)

const profile = ref<CareerProfile>({ ...EMPTY_PROFILE })
const customDims = ref<string[]>([])
const savingDims = ref(false)

const trackOptions = computed(() =>
  tracks.value.map((t) => ({ label: `${t.name}（${t.tagline}）`, value: t.key })),
)
const resumeOptions = computed(() =>
  resumes.value.map((r) => ({ label: `${r.is_default ? '★ ' : ''}${r.name}`, value: r.id })),
)
const currentTrack = computed(() => tracks.value.find((t) => t.key === currentKey.value) ?? null)
/** AI 画像里识别的方向与当前方向不一致时提示一键切换 */
const profileTrackDiff = computed(
  () =>
    profile.value.track_key &&
    profile.value.track_key !== currentKey.value &&
    tracks.value.some((t) => t.key === profile.value.track_key),
)
const profileTrackName = computed(
  () => tracks.value.find((t) => t.key === profile.value.track_key)?.name ?? '',
)

async function loadAll() {
  loading.value = true
  try {
    const [overview, p] = await Promise.all([api.careerOverview(), api.getProfile()])
    tracks.value = overview.tracks
    currentKey.value = overview.current_key
    profile.value = { ...EMPTY_PROFILE, ...p }
    customDims.value = (p as any).custom_dimensions ?? []
  } catch (e) {
    message.error((e as Error).message || '加载失败')
  } finally {
    loading.value = false
  }
}

onMounted(async () => {
  await loadAll()
  // 按角色判断（role=admin，含演示账号 show），而非仅内置 admin；简历按 user_id 隔离，各管理员用自己名下的
  if (isAdmin.value) {
    try {
      resumes.value = (await api.listResumes()).items
      const def = resumes.value.find((r) => r.is_default) ?? resumes.value[0]
      genResumeId.value = def?.id ?? null
    } catch {
      /* 简历列表失败不阻塞页面 */
    }
  }
})

async function saveProfile() {
  saving.value = true
  try {
    const payload: Partial<CareerProfile> = {
      headline: profile.value.headline,
      years: profile.value.years,
      skills: profile.value.skills,
      strengths: profile.value.strengths,
      gaps: profile.value.gaps,
      summary: profile.value.summary,
    }
    if (profile.value.track_key) payload.track_key = profile.value.track_key
    const saved = await api.saveProfile(payload)
    profile.value = { ...EMPTY_PROFILE, ...saved }
    customDims.value = (saved as any).custom_dimensions ?? []
    message.success('职业画像已保存，后续 AI 出题 / 体检 / 模拟面试都会参考它')
  } catch (e) {
    message.error((e as Error).message || '保存失败')
  } finally {
    saving.value = false
  }
}

async function generateProfile() {
  generating.value = true
  try {
    const saved = await api.generateProfile(genResumeId.value ?? undefined)
    profile.value = { ...EMPTY_PROFILE, ...saved }
    customDims.value = (saved as any).custom_dimensions ?? []
    message.success(
      profileTrackDiff.value
        ? `画像已生成，识别方向为「${profileTrackName.value}」`
        : '画像已生成，可手动修改后保存',
    )
  } catch (e) {
    message.error((e as Error).message || '生成失败')
  } finally {
    generating.value = false
  }
}

async function switchTo(key: string) {
  switching.value = key
  try {
    const res = await api.switchTrack(key)
    currentKey.value = res.current_key
    message.success(`已切换到「${tracks.value.find((t) => t.key === key)?.name ?? key}」，全站 AI 功能按新方向出题`)
  } catch (e) {
    message.error((e as Error).message || '切换失败')
  } finally {
    switching.value = ''
  }
}

async function syncSkillsToDims() {
  if (!profile.value.skills.length) {
    message.warning('画像里还没有技能栈，先填写或生成画像')
    return
  }
  savingDims.value = true
  try {
    const merged = [...new Set([...customDims.value, ...profile.value.skills])]
    const res = await api.saveCustomDimensions(merged)
    customDims.value = res.dimensions
    message.success(`已把 ${profile.value.skills.length} 项技能同步为考察维度（预设维度不受影响）`)
  } catch (e) {
    message.error((e as Error).message || '同步失败')
  } finally {
    savingDims.value = false
  }
}

async function saveDims() {
  savingDims.value = true
  try {
    const res = await api.saveCustomDimensions(customDims.value)
    customDims.value = res.dimensions
    message.success('自定义维度已保存')
  } catch (e) {
    message.error((e as Error).message || '保存失败')
  } finally {
    savingDims.value = false
  }
}
</script>

<template>
  <div class="h-full overflow-y-auto">
    <div class="fade-up flex items-end justify-between px-7 pb-4 pt-6 max-md:px-4 max-md:pt-4">
      <div>
        <h1 class="text-[21px] font-bold tracking-tight text-zinc-900">职业画像</h1>
        <p class="mt-1 text-[13px] text-zinc-400">职业方向、技能栈与交叉背景——全站 AI 功能的「了解你」入口</p>
      </div>
    </div>

    <div class="fade-up px-7 pb-10 max-md:px-4">
      <div class="rounded-2xl border border-zinc-100 bg-white p-6 max-md:p-4">
        <n-tabs v-model:value="activeTab" type="line" animated>
          <!-- 职业画像 -->
          <n-tab-pane name="profile" tab="职业画像">
            <div class="mb-5 flex flex-wrap items-center gap-2 rounded-xl bg-zinc-50 px-4 py-3 max-md:flex-col max-md:items-start">
              <n-tag size="small" type="primary" :bordered="false">当前方向：{{ currentTrack?.name ?? '—' }}</n-tag>
              <span v-if="profile.headline" class="text-[13px] text-zinc-600">{{ profile.headline }}</span>
              <span v-else class="text-[13px] text-zinc-400">画像还是空的——用下面的按钮从简历生成，或手动填写</span>
            </div>

            <div
              v-if="profileTrackDiff"
              class="mb-5"
            >
              <n-alert type="info" :show-icon="false">
                <div class="flex flex-wrap items-center gap-3">
                  <span>AI 从简历识别出的方向是「{{ profileTrackName }}」，与当前方向不同。</span>
                  <n-button
                    v-if="isBuiltinAdmin"
                    size="tiny"
                    type="primary"
                    :loading="switching === profile.track_key"
                    @click="switchTo(profile.track_key)"
                  >
                    切换到该方向
                  </n-button>
                  <span v-else class="text-[12px] text-zinc-400">如需切换全站方向，请联系管理员</span>
                </div>
              </n-alert>
            </div>

            <div class="mb-6 rounded-xl border border-dashed border-indigo-200 bg-indigo-50/50 px-4 py-3 max-md:flex-col">
              <div class="flex flex-wrap items-center gap-3">
                <span class="text-[13px] font-semibold text-indigo-900">从简历生成画像</span>
                <n-select
                  v-model:value="genResumeId"
                  :options="resumeOptions"
                  placeholder="选择简历（默认为 ★ 默认简历）"
                  size="small"
                  clearable
                  class="w-[280px] max-md:w-full"
                />
                <n-button size="small" type="primary" secondary :loading="generating" :disabled="!resumes.length" @click="generateProfile">
                  AI 生成画像
                </n-button>
                <span class="text-[12px] text-indigo-500/80 max-md:hidden">把简历设为默认时会自动生成；此处可手动重生成</span>
              </div>
            </div>

            <div class="max-w-[680px]">
              <div class="mb-4">
                <div class="mb-1.5 text-[13px] font-semibold text-zinc-800">一句话画像</div>
                <n-input
                  v-model:value="profile.headline"
                  placeholder="如：8 年 Java 后端，主攻高并发与稳定性，近两年在做大模型应用"
                />
              </div>
              <div class="mb-4">
                <div class="mb-1.5 text-[13px] font-semibold text-zinc-800">工作年限</div>
                <n-input-number v-model:value="profile.years" :min="0" :max="60" class="w-[160px] max-md:w-full" placeholder="年" />
              </div>
              <div class="mb-4">
                <div class="mb-1.5 text-[13px] font-semibold text-zinc-800">
                  技能栈
                  <span class="ml-2 font-normal text-zinc-400">交叉背景（如 后端+AI、测试+交付）直接写在这里</span>
                </div>
                <n-dynamic-tags v-model:value="profile.skills" />
              </div>
              <div class="mb-4">
                <div class="mb-1.5 text-[13px] font-semibold text-zinc-800">优势</div>
                <n-dynamic-tags v-model:value="profile.strengths" />
              </div>
              <div class="mb-4">
                <div class="mb-1.5 text-[13px] font-semibold text-zinc-800">短板 / 空白</div>
                <n-dynamic-tags v-model:value="profile.gaps" />
              </div>
              <div class="mb-5">
                <div class="mb-1.5 text-[13px] font-semibold text-zinc-800">职业概述</div>
                <n-input
                  v-model:value="profile.summary"
                  type="textarea"
                  :autosize="{ minRows: 2, maxRows: 5 }"
                  placeholder="两三句：方向、领域、层级、核心亮点"
                />
              </div>
              <n-button type="primary" size="small" :loading="saving" @click="saveProfile">保存画像</n-button>
            </div>
          </n-tab-pane>

          <!-- 职业方向：全局一套，切换仅限管理员 -->
          <n-tab-pane name="tracks" tab="职业方向">
            <div class="mb-2 text-[13px] text-zinc-500">
              当前方向决定 AI 的出题框架（考察维度、轮次侧重、教练人设）。交叉背景不靠切换方向解决——写进「职业画像」的技能栈即可。
              <span v-if="!isBuiltinAdmin">方向由管理员统一设置。</span>
            </div>
            <div class="grid grid-cols-2 gap-3 max-md:grid-cols-1">
              <div
                v-for="t in tracks"
                :key="t.key"
                class="rounded-xl border p-4 transition-colors"
                :class="t.key === currentKey ? 'border-indigo-300 bg-indigo-50/60' : 'border-zinc-200 bg-white hover:border-zinc-200'"
              >
                <div class="flex items-center justify-between gap-2">
                  <div class="text-[14px] font-bold text-zinc-800">{{ t.name }}</div>
                  <n-tag v-if="t.key === currentKey" size="small" type="primary" :bordered="false">当前</n-tag>
                  <n-button
                    v-else-if="isBuiltinAdmin"
                    size="tiny"
                    :loading="switching === t.key"
                    @click="switchTo(t.key)"
                  >
                    设为当前
                  </n-button>
                </div>
                <div class="mt-0.5 text-[12px] text-zinc-400">{{ t.tagline }}</div>
                <div class="mt-2.5 flex flex-wrap gap-1">
                  <span
                    v-for="d in t.dimensions.filter((d) => d !== '其他')"
                    :key="d"
                    class="rounded border border-zinc-200 bg-zinc-50 px-1.5 py-0.5 text-[11px] text-zinc-500"
                  >{{ d }}</span>
                </div>
              </div>
            </div>

            <div v-if="isBuiltinAdmin" class="mt-7 border-t border-zinc-100 pt-5">
              <div class="mb-1 text-[13px] font-semibold text-zinc-800">自定义考察维度</div>
              <div class="mb-2.5 text-[12px] text-zinc-400">
                追加在当前方向预设之后的维度（如「大模型」「数通/网络协议」「交付/项目管理」），录题与 AI 归类都会使用。
              </div>
              <n-dynamic-tags v-model:value="customDims" />
              <n-button class="mt-3" size="small" :loading="savingDims" @click="saveDims">保存自定义维度</n-button>
            </div>

            <div v-if="isBuiltinAdmin" class="mt-5 border-t border-zinc-100 pt-5">
              <div class="mb-1 text-[13px] font-semibold text-zinc-800">技能栈 → 考察维度</div>
              <div class="mb-2.5 text-[12px] text-zinc-400">把画像里的技能栈一键追加为自定义维度，让交叉背景进入出题范围。</div>
              <n-button size="small" secondary type="primary" :loading="savingDims" @click="syncSkillsToDims">
                同步画像技能为维度
              </n-button>
            </div>
          </n-tab-pane>
        </n-tabs>
      </div>
    </div>
  </div>
</template>
