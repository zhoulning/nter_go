# -*- coding: utf-8 -*-
"""一次性补丁：题库列表页增加来源标签 / AI 答案按钮 / 口述简答展示。"""
import io

path = 'frontend/src/views/QuestionBankView.vue'
with io.open(path, encoding='utf-8') as f:
    c = f.read()

# 1) 图标导入 + AI 状态
old = "import { AddOutline, SearchOutline } from '@vicons/ionicons5'"
new = "import { AddOutline, SearchOutline, SparklesOutline } from '@vicons/ionicons5'"
assert old in c, 'p1'
c = c.replace(old, new, 1)

old = "const modalShow = ref(false)\nconst editing = ref<Question | null>(null)"
new = "const modalShow = ref(false)\nconst editing = ref<Question | null>(null)\nconst aiBusyId = ref<number | null>(null)"
assert old in c, 'p2'
c = c.replace(old, new, 1)

# 2) 来源摘要 + AI 生成函数
old = "function openCreate() {"
new = """/** 来源摘要：单来源显示「公司 · 轮次」，多来源显示「A 等 N 处」 */
const sourceSummary = computed(() => (q: Question) => {
  const srcs = q.sources ?? []
  if (srcs.length === 0) return ''
  const parts = srcs.map(
    (s) => `${s.company ?? '未知公司'}${s.round_type ? ` · ${ROUND_LABEL[s.round_type] ?? '面试'}` : ''}`,
  )
  if (parts.length === 1) return parts[0]
  return `${parts[0]} 等 ${parts.length} 处`
})

function sourceCompanies(q: Question): string[] {
  return [...new Set((q.sources ?? []).map((s) => s.company ?? ''))] as string[]
}

async function genAnswerFor(q: Question) {
  aiBusyId.value = q.id
  try {
    const res = await api.generateAnswer({ question_id: q.id })
    if (res.answer_spoken || res.answer_brief) {
      message.success('已生成口述版与简答版答案')
      await load()
    } else {
      message.warning('AI 没有返回有效答案，请重试')
    }
  } catch (e) {
    message.error((e as Error).message || 'AI 生成失败', { duration: 6000 })
  } finally {
    aiBusyId.value = null
  }
}

function openCreate() {"""
assert old in c, 'p3'
c = c.replace(old, new, 1)

# 3) 搜索覆盖来源公司与简历名
old = """    list = list.filter((q) =>
      [q.content, q.dimension, q.opportunity?.company].some((v) =>
        v?.toLowerCase().includes(kw),
      ),
    )"""
new = """    list = list.filter((q) => {
      const hay = [
        q.content,
        q.dimension,
        q.opportunity?.company,
        q.resume_name,
        ...(q.sources ?? []).map((s) => s.company ?? ''),
      ]
      return hay.some((v) => v?.toLowerCase().includes(kw))
    })"""
assert old in c, 'p4'
c = c.replace(old, new, 1)

# 4) 卡片 meta：来源标签
old = """            <span class="ml-auto text-[11px] text-zinc-400">
              {{ QUESTION_SOURCE_LABEL[q.source] }}
              <template v-if="q.opportunity">· {{ q.opportunity.company }}</template>
            </span>"""
new = """            <span class="ml-auto flex items-center gap-1.5">
              <span
                v-if="sourceSummary(q)"
                class="flex items-center gap-1 rounded-full border border-zinc-200 bg-zinc-50 py-0.5 pl-0.5 pr-2"
                :title="(q.sources ?? []).map((s) => `${s.company ?? ''}${s.round_type ? ` · ${ROUND_LABEL[s.round_type] ?? ''}` : ''}`).join('，')"
              >
                <span class="flex -space-x-1.5">
                  <span
                    v-for="(comp, ci) in sourceCompanies(q).slice(0, 3)"
                    :key="ci"
                    class="grid h-4 w-4 place-items-center rounded-full text-[8px] font-bold text-white ring-1 ring-white"
                    :style="{ background: avatarGradient(comp) }"
                  >
                    {{ comp.slice(0, 1) }}
                  </span>
                </span>
                <span class="max-w-[150px] truncate text-[10.5px] text-zinc-500">
                  {{ sourceSummary(q) }}
                </span>
              </span>
              <span class="text-[11px] text-zinc-400">{{ QUESTION_SOURCE_LABEL[q.source] }}</span>
            </span>"""
assert old in c, 'p5'
c = c.replace(old, new, 1)

# 5) 答案展示：口述版/简答版
old = """            <details v-if="q.answer_key">
              <summary class="cursor-pointer select-none text-[11.5px] text-zinc-400 hover:text-zinc-600">
                参考答案要点
              </summary>
              <p class="mt-1 whitespace-pre-wrap rounded-lg bg-emerald-50/60 px-2.5 py-2 text-[12px] leading-relaxed text-zinc-600">
                {{ q.answer_key }}
              </p>
            </details>
          </div>"""
new = """            <details v-if="q.answer_spoken">
              <summary class="cursor-pointer select-none text-[11.5px] text-indigo-400 hover:text-indigo-600">
                ✨ AI 口述版答案
              </summary>
              <p class="mt-1 whitespace-pre-wrap rounded-lg bg-indigo-50/60 px-2.5 py-2 text-[12px] leading-relaxed text-zinc-600">
                {{ q.answer_spoken }}
              </p>
            </details>
            <details v-if="q.answer_brief">
              <summary class="cursor-pointer select-none text-[11.5px] text-sky-400 hover:text-sky-600">
                ✨ AI 简答版要点
              </summary>
              <p class="mt-1 whitespace-pre-wrap rounded-lg bg-sky-50/60 px-2.5 py-2 text-[12px] leading-relaxed text-zinc-600">
                {{ q.answer_brief }}
              </p>
            </details>
            <details v-if="q.answer_key">
              <summary class="cursor-pointer select-none text-[11.5px] text-zinc-400 hover:text-zinc-600">
                参考答案要点
              </summary>
              <p class="mt-1 whitespace-pre-wrap rounded-lg bg-emerald-50/60 px-2.5 py-2 text-[12px] leading-relaxed text-zinc-600">
                {{ q.answer_key }}
              </p>
            </details>
          </div>"""
assert old in c, 'p6'
c = c.replace(old, new, 1)

# 6) 答案区显隐条件扩展
old = """          <div v-if="q.my_answer || q.answer_key" class="mt-2.5 flex flex-col gap-1.5">"""
new = """          <div
            v-if="q.my_answer || q.answer_key || q.answer_spoken || q.answer_brief"
            class="mt-2.5 flex flex-col gap-1.5"
          >"""
assert old in c, 'p7'
c = c.replace(old, new, 1)

# 7) 底部：关联简历标记
old = """              <span v-if="q.self_rating" class="text-[11px] text-zinc-400">自评 {{ q.self_rating }} 分</span>"""
new = """              <span v-if="q.self_rating" class="text-[11px] text-zinc-400">自评 {{ q.self_rating }} 分</span>
              <span
                v-if="q.resume_name"
                class="max-w-[110px] truncate rounded bg-zinc-100 px-1 py-0.5 text-[10.5px] text-zinc-500"
                :title="`关联简历：${q.resume_name}`"
              >
                📄 {{ q.resume_name }}
              </span>"""
assert old in c, 'p8'
c = c.replace(old, new, 1)

# 8) 操作行：AI 按钮
old = """              <n-button size="tiny" quaternary type="primary" @click="openEdit(q)">编辑</n-button>"""
new = """              <n-button
                size="tiny"
                quaternary
                type="primary"
                :loading="aiBusyId === q.id"
                @click="genAnswerFor(q)"
              >
                <template #icon>
                  <n-icon :component="SparklesOutline" :size="12" />
                </template>
                AI 答案
              </n-button>
              <n-button size="tiny" quaternary type="primary" @click="openEdit(q)">编辑</n-button>"""
assert old in c, 'p9'
c = c.replace(old, new, 1)

# 9) 导入补充
old = """import {
  DIFFICULTY_META,
  MASTERY_META,
  QUESTION_SOURCE_LABEL,
} from '../types'"""
new = """import {
  DIFFICULTY_META,
  MASTERY_META,
  QUESTION_SOURCE_LABEL,
  ROUND_LABEL,
  avatarGradient,
} from '../types'"""
assert old in c, 'p10'
c = c.replace(old, new, 1)

with io.open(path, 'w', encoding='utf-8', newline='\n') as f:
    f.write(content := c)
print('QuestionBankView updated')
