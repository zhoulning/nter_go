<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import {
  NButton,
  NDatePicker,
  NForm,
  NFormItem,
  NInput,
  NModal,
  NSelect,
  useMessage,
} from 'naive-ui'
import type { FormInst } from 'naive-ui'
import { api } from '../api'
import type { Opportunity, RoundEvent, RoundPayload } from '../api'
import { ROUND_LABEL, ROUND_RESULT_META } from '../types'
import { toLocalIso } from '../utils'

const props = defineProps<{
  show: boolean
  round: RoundEvent | null
  defaultDate: string | null
  opportunities: Opportunity[]
}>()
const emit = defineEmits<{
  (e: 'update:show', v: boolean): void
  (e: 'saved', round: RoundEvent, isNew: boolean): void
}>()

const message = useMessage()
const formRef = ref<FormInst | null>(null)
const saving = ref(false)
const isEdit = computed(() => !!props.round)

const emptyForm = () => ({
  opportunity_id: null as number | null,
  round_type: 'first',
  scheduled_at: null as number | null,
  result: 'pending',
  note: '',
})

const form = reactive(emptyForm())

watch(
  () => props.show,
  (v) => {
    if (!v) return
    if (props.round) {
      Object.assign(form, {
        opportunity_id: props.round.opportunity_id,
        round_type: props.round.round_type,
        scheduled_at: props.round.scheduled_at
          ? new Date(props.round.scheduled_at).getTime()
          : null,
        result: props.round.result,
        note: props.round.note ?? '',
      })
    } else {
      const base = props.defaultDate ? new Date(`${props.defaultDate}T10:00:00`) : null
      Object.assign(form, {
        ...emptyForm(),
        scheduled_at: base ? base.getTime() : Date.now(),
      })
    }
  },
)

const rules = {
  opportunity_id: { required: true, message: '请选择关联岗位', trigger: 'change' },
  scheduled_at: {
    validator: () => form.scheduled_at != null,
    message: '请选择面试时间',
    trigger: 'change',
  },
}

const opportunityOptions = computed(() =>
  props.opportunities.map((o) => ({
    label: `${o.company} · ${o.position}`,
    value: o.id,
  })),
)
const roundTypeOptions = Object.entries(ROUND_LABEL).map(([value, label]) => ({
  label,
  value,
}))
const resultOptions = Object.entries(ROUND_RESULT_META).map(([value, meta]) => ({
  label: meta.label,
  value,
}))

async function submit() {
  try {
    await formRef.value?.validate()
  } catch {
    return
  }
  saving.value = true
  try {
    const payload: RoundPayload = {
      opportunity_id: form.opportunity_id!,
      round_type: form.round_type,
      scheduled_at: toLocalIso(new Date(form.scheduled_at!)),
      result: form.result,
      note: form.note.trim() || null,
    }
    const saved = isEdit.value
      ? await api.updateRound(props.round!.id, payload)
      : await api.createRound(payload)
    const opp = props.opportunities.find((o) => o.id === payload.opportunity_id)
    emit('saved', saved, !isEdit.value)
    message.success(
      isNewText(isEdit.value, opp?.company ?? '', saved.round_type),
    )
    emit('update:show', false)
  } catch (e) {
    message.error((e as Error).message || '保存失败')
  } finally {
    saving.value = false
  }
}

function isNewText(isEdit: boolean, company: string, roundType: string): string {
  const label = ROUND_LABEL[roundType] ?? '面试'
  return isEdit ? `已更新「${company} · ${label}」` : `已排期「${company} · ${label}」`
}
</script>

<template>
  <n-modal :show="show" transform-origin="center" @update:show="emit('update:show', $event)">
    <div class="modal-card">
      <div class="mb-5">
        <h2 class="text-[16px] font-bold text-zinc-900">
          {{ isEdit ? '编辑面试安排' : '新增面试安排' }}
        </h2>
        <p class="mt-0.5 text-[12px] text-zinc-400">排期后会在岗位卡片与日历中同步展示</p>
      </div>

      <n-form ref="formRef" :model="form" :rules="rules" label-placement="top" size="small" :show-require-mark="false">
        <n-form-item label="关联岗位" path="opportunity_id">
          <n-select
            v-model:value="form.opportunity_id"
            filterable
            :options="opportunityOptions"
            placeholder="选择公司 / 岗位"
          />
        </n-form-item>
        <div class="grid grid-cols-2 gap-x-4">
          <n-form-item label="轮次" path="round_type">
            <n-select v-model:value="form.round_type" :options="roundTypeOptions" />
          </n-form-item>
          <n-form-item label="结果" path="result">
            <n-select v-model:value="form.result" :options="resultOptions" />
          </n-form-item>
        </div>
        <n-form-item label="面试时间" path="scheduled_at">
          <n-date-picker
            v-model:value="form.scheduled_at"
            type="datetime"
            style="width: 100%"
            format="yyyy-MM-dd HH:mm"
            placeholder="选择日期与时间"
          />
        </n-form-item>
        <n-form-item label="备注" path="note">
          <n-input
            v-model:value="form.note"
            type="textarea"
            :rows="2"
            placeholder="选填：面试形式、面试官、注意事项等"
          />
        </n-form-item>
      </n-form>

      <div class="mt-2 flex justify-end gap-2.5">
        <n-button quaternary @click="emit('update:show', false)">取消</n-button>
        <n-button type="primary" class="!px-5" :loading="saving" @click="submit">
          {{ isEdit ? '保存' : '添加' }}
        </n-button>
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
