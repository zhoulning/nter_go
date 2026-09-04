<script setup lang="ts">
import { computed } from 'vue'
import { NDropdown } from 'naive-ui'
import { EllipsisHorizontalOutline, LocationOutline, TimeOutline } from '@vicons/ionicons5'
import type { Opportunity } from '../types'
import { PRIORITY_CLASS, ROUND_LABEL, avatarGradient } from '../types'
import { daysSince, daysUntil, eventLabel, shortDate } from '../utils'

const props = defineProps<{ opp: Opportunity; dragging?: boolean }>()
const emit = defineEmits<{
  (e: 'detail'): void
  (e: 'edit'): void
  (e: 'delete'): void
  (e: 'dragstart', ev: DragEvent): void
  (e: 'dragend'): void
}>()

const menuOptions = [
  { label: '详情', key: 'detail' },
  { label: '编辑', key: 'edit' },
  { label: '删除', key: 'delete', props: { style: 'color: #e11d48' } },
]

function onMenu(key: string | number) {
  if (key === 'detail') emit('detail')
  else if (key === 'edit') emit('edit')
  else if (key === 'delete') emit('delete')
}

const initial = computed(() => props.opp.company.slice(0, 1).toUpperCase())

const nextEvent = computed(() => {
  const ev = props.opp.next_event
  if (!ev?.scheduled_at) return null
  return {
    label: ROUND_LABEL[ev.round_type] ?? '面试',
    when: eventLabel(ev.scheduled_at),
    chipClass: nextChipClass(ev.scheduled_at),
  }
})

/** 下场面试临近程度 → 颜色（1 天内玫红、3 天内琥珀、更远天蓝） */
function nextChipClass(dt: string): string {
  const d = daysUntil(dt) ?? 99
  if (d <= 1) return 'bg-rose-50 text-rose-600'
  if (d <= 3) return 'bg-amber-50 text-amber-600'
  return 'bg-sky-50 text-sky-600'
}
</script>

<template>
  <article
    draggable="true"
    class="group relative cursor-grab select-none rounded-xl border border-zinc-200/80 bg-white p-3.5 shadow-[0_1px_2px_rgba(16,24,40,0.05)] transition-all hover:-translate-y-px hover:shadow-[0_10px_24px_-8px_rgba(16,24,40,0.18)] active:cursor-grabbing"
    :class="dragging && 'card-dragging'"
    @click="emit('detail')"
    @dragstart="emit('dragstart', $event)"
    @dragend="emit('dragend')"
  >
    <div class="flex items-start gap-2.5">
      <div
        class="grid h-9 w-9 shrink-0 place-items-center rounded-[10px] text-[15px] font-bold text-white shadow-sm"
        :style="{ background: avatarGradient(opp.company) }"
      >
        {{ initial }}
      </div>
      <div class="min-w-0 flex-1">
        <div class="flex items-center gap-1.5">
          <h3 class="truncate text-[13.5px] font-semibold text-zinc-800">{{ opp.company }}</h3>
          <span
            class="ml-auto shrink-0 rounded-md border px-1.5 text-[10.5px] font-bold leading-[18px]"
            :class="PRIORITY_CLASS[opp.priority] ?? PRIORITY_CLASS.B"
          >
            {{ opp.priority }}
          </span>
        </div>
        <p class="mt-0.5 truncate text-[12px] text-zinc-500">{{ opp.position }}</p>
      </div>
      <n-dropdown
        trigger="click"
        placement="bottom-end"
        :options="menuOptions"
        @select="onMenu"
      >
        <button
          class="-mr-1 grid h-6 w-6 shrink-0 place-items-center rounded-md text-zinc-400 opacity-0 transition-all hover:bg-zinc-100 hover:text-zinc-600 focus:opacity-100 group-hover:opacity-100"
          @click.stop
        >
          <n-icon :component="EllipsisHorizontalOutline" :size="15" />
        </button>
      </n-dropdown>
    </div>

    <div class="mt-2.5 flex flex-wrap items-center gap-1.5">
      <span
        v-if="opp.city"
        class="inline-flex items-center gap-1 rounded-md bg-zinc-50 px-1.5 py-0.5 text-[11px] text-zinc-500"
      >
        <n-icon :component="LocationOutline" :size="11" />
        {{ opp.city }}
      </span>
      <span
        v-if="opp.salary_range"
        class="rounded-md bg-emerald-50 px-1.5 py-0.5 text-[11px] font-medium text-emerald-600"
      >
        {{ opp.salary_range }}
      </span>
      <span
        v-if="opp.channel"
        class="rounded-md bg-zinc-50 px-1.5 py-0.5 text-[11px] text-zinc-400"
      >
        {{ opp.channel }}
      </span>
    </div>

    <div class="mt-3 flex items-center justify-between gap-2 border-t border-zinc-100 pt-2.5">
      <span
        v-if="nextEvent"
        class="inline-flex min-w-0 items-center gap-1 rounded-md px-1.5 py-0.5 text-[11px] font-medium"
        :class="nextEvent.chipClass"
      >
        <n-icon :component="TimeOutline" :size="11" class="shrink-0" />
        <span class="truncate">{{ nextEvent.label }} · {{ nextEvent.when }}</span>
      </span>
      <span v-else class="text-[11px] text-zinc-300">暂无安排</span>
      <span class="flex shrink-0 items-center gap-1 text-[11px] text-zinc-400">
        <template v-if="opp.applied_at">
          <span>投递 {{ shortDate(opp.applied_at) }}</span>
          <span class="text-zinc-300">·</span>
        </template>
        <span>停留 {{ daysSince(opp.status_changed_at) }} 天</span>
      </span>
    </div>
  </article>
</template>
