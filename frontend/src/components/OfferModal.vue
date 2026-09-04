<script setup lang="ts">
import { reactive, ref, watch } from 'vue'
import { NButton, NForm, NFormItem, NInput, NModal, NInputNumber, NRate, useDialog, useMessage } from 'naive-ui'
import { api } from '../api'
import type { OfferInfo, OfferPayload } from '../api'
import type { Opportunity } from '../types'
import { OFFER_DIMS } from '../types'

const props = defineProps<{ show: boolean; opportunity: Opportunity | null; existing: OfferInfo | null }>()
const emit = defineEmits<{
  (e: 'update:show', v: boolean): void
  (e: 'saved', offer: OfferInfo): void
}>()

const message = useMessage()
const dialog = useDialog()
const saving = ref(false)

const emptyForm = () => ({
  monthly_salary: null as number | null,
  months: 15 as number | null,
  signing_bonus: '',
  stock: '',
  welfare: '',
  overtime: '',
  commute: '',
  score_salary: 3,
  score_platform: 3,
  score_growth: 3,
  score_worklife: 3,
  score_commute: 3,
  note: '',
})

const form = reactive(emptyForm())

watch(
  () => props.show,
  (v) => {
    if (!v) return
    const src = props.existing
    Object.assign(form, {
      monthly_salary: src?.monthly_salary ?? null,
      months: src?.months ?? 15,
      signing_bonus: src?.signing_bonus ?? '',
      stock: src?.stock ?? '',
      welfare: src?.welfare ?? '',
      overtime: src?.overtime ?? '',
      commute: src?.commute ?? '',
      score_salary: src?.score_salary ?? 3,
      score_platform: src?.score_platform ?? 3,
      score_growth: src?.score_growth ?? 3,
      score_worklife: src?.score_worklife ?? 3,
      score_commute: src?.score_commute ?? 3,
      note: src?.note ?? '',
    })
  },
)

async function save() {
  if (!props.opportunity) return
  saving.value = true
  try {
    const payload: OfferPayload = {
      monthly_salary: form.monthly_salary,
      months: form.months,
      signing_bonus: form.signing_bonus.trim() || null,
      stock: form.stock.trim() || null,
      welfare: form.welfare.trim() || null,
      overtime: form.overtime.trim() || null,
      commute: form.commute.trim() || null,
      score_salary: form.score_salary,
      score_platform: form.score_platform,
      score_growth: form.score_growth,
      score_worklife: form.score_worklife,
      score_commute: form.score_commute,
      note: form.note.trim() || null,
    }
    const saved = await api.upsertOffer(props.opportunity.id, payload)
    message.success(`已保存「${props.opportunity.company}」的 Offer 信息`)
    emit('saved', saved)
    emit('update:show', false)
  } catch (e) {
    message.error((e as Error).message || '保存失败')
  } finally {
    saving.value = false
  }
}

function clearOffer() {
  if (!props.opportunity) return
  const opp = props.opportunity
  dialog.warning({
    title: '清除 Offer 记录',
    content: `确定清除「${opp.company}」的 Offer 记录吗？`,
    positiveText: '清除',
    negativeText: '取消',
    onPositiveClick: async () => {
      try {
        await api.deleteOffer(opp.id)
        message.success('已清除')
        emit('saved', { ...({} as OfferInfo), opportunity_id: opp.id } as OfferInfo)
        emit('update:show', false)
      } catch (e) {
        message.error((e as Error).message || '清除失败')
      }
    },
  })
}
</script>

<template>
  <n-modal :show="show" transform-origin="center" @update:show="emit('update:show', $event)">
    <div class="modal-card">
      <div class="mb-4">
        <h2 class="text-[16px] font-bold text-zinc-900">
          Offer 信息 · {{ opportunity?.company }}
        </h2>
        <p class="mt-0.5 text-[12px] text-zinc-400">
          {{ opportunity?.position }}{{ opportunity?.city ? ` · ${opportunity.city}` : '' }}
        </p>
      </div>

      <n-form label-placement="top" size="small" :show-require-mark="false">
        <div class="grid grid-cols-2 gap-x-4">
          <n-form-item label="月薪（K）">
            <n-input-number
              v-model:value="form.monthly_salary"
              class="w-full"
              :min="1"
              :max="500"
              placeholder="如：40"
            />
          </n-form-item>
          <n-form-item label="薪资月数">
            <n-input-number
              v-model:value="form.months"
              class="w-full"
              :min="10"
              :max="24"
              placeholder="如：15"
            />
          </n-form-item>
          <n-form-item label="签字费 / 奖金">
            <n-input v-model:value="form.signing_bonus" placeholder="没有可填「无」" />
          </n-form-item>
          <n-form-item label="股票 / 期权">
            <n-input v-model:value="form.stock" placeholder="如：期权 4 年归属" />
          </n-form-item>
          <n-form-item label="公积金 / 福利">
            <n-input v-model:value="form.welfare" placeholder="如：公积金 12%" />
          </n-form-item>
          <n-form-item label="加班情况">
            <n-input v-model:value="form.overtime" placeholder="如：大小周 / 965" />
          </n-form-item>
          <n-form-item label="通勤情况" path="commute">
            <n-input v-model:value="form.commute" placeholder="如：地铁 45 分钟" />
          </n-form-item>
        </div>

        <div class="mt-1 rounded-xl bg-zinc-50 px-4 py-3">
          <div class="mb-2 text-[12px] font-semibold text-zinc-600">主观评分（1-5）</div>
          <div class="grid grid-cols-1 gap-y-2 sm:grid-cols-2 lg:grid-cols-3">
            <div v-for="dim in OFFER_DIMS" :key="dim.key" class="flex items-center justify-between gap-2 pr-3">
              <span class="text-[12.5px] text-zinc-600">{{ dim.label }}</span>
              <n-rate v-model:value="form[dim.key]" :size="16" />
            </div>
          </div>
        </div>

        <n-form-item label="备注" class="mt-2">
          <n-input
            v-model:value="form.note"
            type="textarea"
            :rows="2"
            placeholder="选填：谈薪过程、HR 承诺等"
          />
        </n-form-item>
      </n-form>

      <div class="mt-2 flex justify-between">
        <n-button v-if="existing" quaternary type="error" @click="clearOffer">清除记录</n-button>
        <div v-else />
        <div class="flex gap-2.5">
          <n-button quaternary @click="emit('update:show', false)">取消</n-button>
          <n-button type="primary" class="!px-5" :loading="saving" @click="save">保存</n-button>
        </div>
      </div>
    </div>
  </n-modal>
</template>

<style scoped>
.modal-card {
  width: 620px;
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
