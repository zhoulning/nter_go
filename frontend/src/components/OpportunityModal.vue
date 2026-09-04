<script setup lang="ts">
import { computed, inject, reactive, ref, watch } from 'vue'
import { NButton, NForm, NFormItem, NInput, NModal, NRadioButton, NRadioGroup, NSelect, useMessage } from 'naive-ui'
import { SparklesOutline } from '@vicons/ionicons5'
import type { FormInst } from 'naive-ui'
import { api } from '../api'
import type { OpportunityPayload } from '../api'
import type { Opportunity } from '../types'
import type { Resume } from '../types'
import { CHANNELS, STATUSES } from '../types'
import { toLocalIso } from '../utils'
import { OPEN_AI_SETTINGS } from '../injectionKeys'

const props = defineProps<{
  show: boolean
  opportunity?: Opportunity | null
  resumes?: Resume[]
}>()
const emit = defineEmits<{
  (e: 'update:show', v: boolean): void
  (e: 'saved', opp: Opportunity, isNew: boolean): void
}>()

const message = useMessage()
const openAiSettings = inject(OPEN_AI_SETTINGS, null)
const formRef = ref<FormInst | null>(null)
const saving = ref(false)
const isEdit = computed(() => !!props.opportunity)

// ---- AI 快速填充 ----
const aiInput = ref('')
const extracting = ref(false)
const aiConfigured = ref<boolean | null>(null)

const emptyForm = () => ({
  company: '',
  position: '',
  department: '',
  city: '',
  address: '',
  salary_range: '',
  channel: null as string | null,
  priority: 'B',
  status: 'wishlist',
  applied_at: null as number | null,
  resume_id: null as number | null,
  jd_text: '',
  note: '',
})

const form = reactive(emptyForm())

watch(
  () => props.show,
  async (v) => {
    if (!v) return
    aiInput.value = ''
    api
      .getAiSettings()
      .then((info) => (aiConfigured.value = info.api_key_configured))
      .catch(() => (aiConfigured.value = null))
    if (props.opportunity) {
      Object.assign(form, {
        company: props.opportunity.company,
        position: props.opportunity.position,
        department: props.opportunity.department ?? '',
        city: props.opportunity.city ?? '',
        address: props.opportunity.address ?? '',
        salary_range: props.opportunity.salary_range ?? '',
        channel: props.opportunity.channel ?? null,
        priority: props.opportunity.priority,
        status: props.opportunity.status,
      applied_at: props.opportunity.applied_at
        ? new Date(props.opportunity.applied_at).getTime()
        : null,
      resume_id: props.opportunity.resume_id,
        jd_text: props.opportunity.jd_text ?? '',
        note: props.opportunity.note ?? '',
      })
    } else {
      Object.assign(form, emptyForm())
    }
  },
)

function applyFields(fields: Record<string, string | null>, hint: string) {
  if (fields.company) form.company = fields.company
  if (fields.position) form.position = fields.position
  if (fields.department) form.department = fields.department
  if (fields.city) form.city = fields.city
  if (fields.address) form.address = fields.address
  if (fields.channel) form.channel = fields.channel
  if (fields.salary_range) form.salary_range = fields.salary_range
  if (fields.jd_text) form.jd_text = fields.jd_text
  message.success(hint)
}

async function extract() {
  const input = aiInput.value.trim()
  extracting.value = true
  try {
    // 智能路由：留空 → 读取专用浏览器当前打开的 BOSS 职位页；链接 → 猎聘直抓 / BOSS 自动提取；文本 → AI
    let payload: { url?: string; text?: string; active_tab?: boolean }
    if (!input) payload = { active_tab: true }
    else if (/^https?:\/\//i.test(input)) payload = { url: input }
    else payload = { text: input }
    const { fields, source } = await api.extractJob(payload)
    const suffix = fields.jd_text ? `（含 ${fields.jd_text.length} 字工作描述）` : ''
    applyFields(fields, `已从${source}填充表单${suffix}，请核对后保存`)
  } catch (e) {
    message.error((e as Error).message || '智能提取失败', { duration: 6000 })
  } finally {
    extracting.value = false
  }
}

const rules = {
  company: { required: true, message: '请填写公司名', trigger: 'blur' },
  position: { required: true, message: '请填写岗位名称', trigger: 'blur' },
}

const resumeOptions = computed(() =>
  (props.resumes ?? []).map((r) => ({
    label: r.is_default ? `★ ${r.name}（默认）` : r.name,
    value: r.id,
  })),
)

const statusOptions = STATUSES.map((s) => ({ label: s.label, value: s.key }))
const channelOptions = CHANNELS.map((c) => ({ label: c, value: c }))

async function submit() {
  try {
    await formRef.value?.validate()
  } catch {
    return
  }
  saving.value = true
  try {
    const payload: OpportunityPayload = {
      company: form.company.trim(),
      position: form.position.trim(),
      department: form.department.trim() || null,
      city: form.city.trim() || null,
      address: form.address.trim() || null,
      salary_range: form.salary_range.trim() || null,
      channel: form.channel,
      priority: form.priority,
      status: form.status,
      applied_at: form.applied_at ? toLocalIso(new Date(form.applied_at)) : null,
      resume_id: form.resume_id,
      jd_text: form.jd_text.trim() || null,
      note: form.note.trim() || null,
    }
    const saved = isEdit.value
      ? await api.updateOpportunity(props.opportunity!.id, payload)
      : await api.createOpportunity(payload)
    emit('saved', saved, !isEdit.value)
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
      <!-- AI 快速填充 -->
      <div class="mb-5 rounded-xl border border-indigo-100 bg-indigo-50/60 p-3.5">
        <div class="mb-2 flex items-center gap-1.5 text-[12.5px] font-semibold text-indigo-600">
          <n-icon :component="SparklesOutline" :size="14" />
          AI 快速填充
        </div>
        <div class="flex gap-2">
          <n-input
            v-model:value="aiInput"
            size="small"
            :disabled="extracting"
            placeholder="粘贴猎聘 / BOSS / 智联 / 脉脉职位链接或 JD 文本；留空则读取专用浏览器当前页面"
          />
          <n-button size="small" type="primary" :loading="extracting" @click="extract">
            智能提取
          </n-button>
        </div>
        <div class="mt-1.5 text-[11px] leading-relaxed text-zinc-400">
          <template v-if="aiConfigured === false">
            尚未配置 AI，<a class="cursor-pointer text-indigo-500" @click="openAiSettings?.()">去设置</a>
            填写 API Key 后即可用；当前也可直接手动填写。
          </template>
          <template v-else>
            猎聘 / BOSS / 智联 / 脉脉 链接自动识别提取；输入框留空点「智能提取」= 读取专用浏览器中当前打开的职位页；也可直接粘贴 JD 文本
          </template>
        </div>
      </div>

      <div class="mb-5">
        <h2 class="text-[16px] font-bold text-zinc-900">
          {{ isEdit ? '编辑岗位' : '新增岗位' }}
        </h2>
        <p class="mt-0.5 text-[12px] text-zinc-400">
          公司 / 岗位为必填，其余信息可稍后补充
        </p>
      </div>

      <n-form
        ref="formRef"
        :model="form"
        :rules="rules"
        label-placement="top"
        size="small"
        :show-require-mark="false"
      >
        <div class="grid grid-cols-2 gap-x-4">
          <n-form-item label="公司" path="company">
            <n-input v-model:value="form.company" placeholder="如：字节跳动" />
          </n-form-item>
          <n-form-item label="岗位" path="position">
            <n-input v-model:value="form.position" placeholder="如：后端开发工程师" />
          </n-form-item>
          <n-form-item label="部门 / 业务线" path="department">
            <n-input v-model:value="form.department" placeholder="选填" />
          </n-form-item>
          <n-form-item label="城市" path="city">
            <n-input v-model:value="form.city" placeholder="选填" />
          </n-form-item>
          <n-form-item label="工作地址" path="address">
            <n-input v-model:value="form.address" placeholder="选填：如 南京建邺区舜禹大厦23F" />
          </n-form-item>
          <n-form-item label="薪资范围" path="salary_range">
            <n-input v-model:value="form.salary_range" placeholder="如：30-50K·16薪" />
          </n-form-item>
          <n-form-item label="渠道" path="channel">
            <n-select v-model:value="form.channel" :options="channelOptions" placeholder="选填" clearable />
          </n-form-item>
          <n-form-item label="优先级" path="priority">
            <n-radio-group v-model:value="form.priority">
              <n-radio-button value="S">S</n-radio-button>
              <n-radio-button value="A">A</n-radio-button>
              <n-radio-button value="B">B</n-radio-button>
            </n-radio-group>
          </n-form-item>
          <n-form-item label="当前状态" path="status">
            <n-select v-model:value="form.status" :options="statusOptions" />
          </n-form-item>
          <n-form-item label="投递时间" path="applied_at">
            <n-date-picker
              v-model:value="form.applied_at"
              type="date"
              clearable
              placeholder="未投递可留空"
              style="width: 100%"
            />
          </n-form-item>
          <n-form-item label="投递简历" path="resume_id">
            <n-select
              v-model:value="form.resume_id"
              filterable
              clearable
              :options="resumeOptions"
              :placeholder="(props.resumes ?? []).length ? '选择简历版本，默认简历带 ★' : '请先到「简历管理」上传'"
              :disabled="!(props.resumes ?? []).length"
            />
          </n-form-item>
        </div>
        <n-form-item label="工作描述" path="jd_text">
          <n-input
            v-model:value="form.jd_text"
            type="textarea"
            :rows="6"
            placeholder="岗位的完整描述：工作职责、任职要求及其他信息（可由 AI 提取或手动粘贴）"
          />
        </n-form-item>
        <n-form-item label="备注" path="note">
          <n-input
            v-model:value="form.note"
            type="textarea"
            :rows="2"
            placeholder="选填：猎头联系方式、面试注意事项等"
          />
        </n-form-item>
      </n-form>

      <div class="mt-2 flex justify-end gap-2.5">
        <n-button quaternary @click="emit('update:show', false)">取消</n-button>
        <n-button type="primary" class="!px-5" :loading="saving" @click="submit">
          {{ isEdit ? '保存' : '创建' }}
        </n-button>
      </div>
    </div>
  </n-modal>
</template>

<style scoped>
.modal-card {
  width: 560px;
  max-width: calc(100vw - 48px);
  max-height: calc(100vh - 48px);
  overflow-y: auto;
  background: #fff;
  border-radius: 16px;
  padding: 24px;
  box-shadow:
    0 20px 50px -12px rgba(16, 24, 40, 0.25),
    0 0 0 1px rgba(16, 24, 40, 0.04);
}
</style>
