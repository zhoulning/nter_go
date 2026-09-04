<script setup lang="ts">
import { computed } from 'vue'

/** 轻量 Markdown 渲染：标题 / 列表 / 引用 / 分隔线 / 围栏代码 / 行内加粗与行内码。
 *  满足调研笔记与报告的展示需要，与项目「零额外前端依赖」保持一致。 */

const props = defineProps<{ source: string }>()

interface Inline {
  t: 'text' | 'b' | 'code'
  s: string
}
interface Row {
  kind: 'h1' | 'h2' | 'h3' | 'p' | 'ul' | 'ol' | 'quote' | 'code' | 'hr'
  inlines: Inline[][]
  code?: string
  n?: number
}

function parseInline(s: string): Inline[] {
  const out: Inline[] = []
  const re = /(\*\*[^*]+\*\*|`[^`]+`)/g
  let last = 0
  let m: RegExpExecArray | null
  while ((m = re.exec(s))) {
    if (m.index > last) out.push({ t: 'text', s: s.slice(last, m.index) })
    const tok = m[0]
    if (tok.startsWith('**')) out.push({ t: 'b', s: tok.slice(2, -2) })
    else out.push({ t: 'code', s: tok.slice(1, -1) })
    last = m.index + tok.length
  }
  if (last < s.length) out.push({ t: 'text', s: s.slice(last) })
  return out.length ? out : [{ t: 'text', s: '' }]
}

const rows = computed<Row[]>(() => {
  const lines = (props.source || '').split('\n')
  const out: Row[] = []
  let para: string[] = []
  let olCounter = 0
  const flush = () => {
    if (para.length) {
      out.push({ kind: 'p', inlines: [parseInline(para.join(' '))] })
      para = []
    }
  }
  for (let i = 0; i < lines.length; i++) {
    const line = lines[i]
    const t = line.trim()
    if (t.startsWith('```')) {
      flush()
      const code: string[] = []
      i++
      while (i < lines.length && !lines[i].trim().startsWith('```')) code.push(lines[i++])
      out.push({ kind: 'code', inlines: [], code: code.join('\n') })
      continue
    }
    if (!t) {
      flush()
      olCounter = 0
      continue
    }
    const h = /^(#{1,6})\s+(.*)$/.exec(t)
    if (h) {
      flush()
      const level = Math.min(h[1].length, 3)
      out.push({
        kind: (level === 1 ? 'h1' : level === 2 ? 'h2' : 'h3') as Row['kind'],
        inlines: [parseInline(h[2])],
      })
      continue
    }
    if (/^(-{3,}|\*{3,})$/.test(t)) {
      flush()
      out.push({ kind: 'hr', inlines: [] })
      continue
    }
    if (/^>\s?/.test(t)) {
      flush()
      out.push({ kind: 'quote', inlines: [parseInline(t.replace(/^>\s?/, ''))] })
      continue
    }
    const ul = /^[-*•]\s+(.*)$/.exec(t)
    if (ul) {
      flush()
      olCounter = 0
      out.push({ kind: 'ul', inlines: [parseInline(ul[1])] })
      continue
    }
    const ol = /^(\d+)[.、)]\s+(.*)$/.exec(t)
    if (ol) {
      flush()
      olCounter += 1
      out.push({ kind: 'ol', inlines: [parseInline(ol[2])], n: olCounter })
      continue
    }
    para.push(t)
  }
  flush()
  return out
})
</script>

<template>
  <div class="text-[13px] leading-relaxed text-zinc-700">
    <template v-for="(row, i) in rows" :key="i">
      <h1 v-if="row.kind === 'h1'" class="mb-1.5 mt-1 text-[16px] font-bold text-zinc-900">
        <template v-for="(seg, j) in row.inlines[0]" :key="j">
          <strong v-if="seg.t === 'b'" class="font-bold">{{ seg.s }}</strong>
          <code v-else-if="seg.t === 'code'" class="rounded bg-zinc-100 px-1 font-mono text-[12px]">{{ seg.s }}</code>
          <span v-else>{{ seg.s }}</span>
        </template>
      </h1>
      <h2 v-else-if="row.kind === 'h2'" class="mb-1.5 mt-4 border-b border-zinc-100 pb-1 text-[14.5px] font-bold text-zinc-900">
        <template v-for="(seg, j) in row.inlines[0]" :key="j">
          <strong v-if="seg.t === 'b'" class="font-bold">{{ seg.s }}</strong>
          <code v-else-if="seg.t === 'code'" class="rounded bg-zinc-100 px-1 font-mono text-[12px]">{{ seg.s }}</code>
          <span v-else>{{ seg.s }}</span>
        </template>
      </h2>
      <h3 v-else-if="row.kind === 'h3'" class="mb-1 mt-3 text-[13.5px] font-semibold text-zinc-800">
        <template v-for="(seg, j) in row.inlines[0]" :key="j">
          <strong v-if="seg.t === 'b'" class="font-bold">{{ seg.s }}</strong>
          <code v-else-if="seg.t === 'code'" class="rounded bg-zinc-100 px-1 font-mono text-[12px]">{{ seg.s }}</code>
          <span v-else>{{ seg.s }}</span>
        </template>
      </h3>
      <p v-else-if="row.kind === 'p'" class="my-1.5">
        <template v-for="(seg, j) in row.inlines[0]" :key="j">
          <strong v-if="seg.t === 'b'" class="font-semibold text-zinc-800">{{ seg.s }}</strong>
          <code v-else-if="seg.t === 'code'" class="rounded bg-zinc-100 px-1 font-mono text-[12px]">{{ seg.s }}</code>
          <span v-else>{{ seg.s }}</span>
        </template>
      </p>
      <div v-else-if="row.kind === 'ul'" class="my-1 flex gap-2">
        <span class="mt-[7px] h-1.5 w-1.5 shrink-0 rounded-full bg-indigo-300" />
        <p class="min-w-0 flex-1">
          <template v-for="(seg, j) in row.inlines[0]" :key="j">
            <strong v-if="seg.t === 'b'" class="font-semibold text-zinc-800">{{ seg.s }}</strong>
            <code v-else-if="seg.t === 'code'" class="rounded bg-zinc-100 px-1 font-mono text-[12px]">{{ seg.s }}</code>
            <span v-else>{{ seg.s }}</span>
          </template>
        </p>
      </div>
      <div v-else-if="row.kind === 'ol'" class="my-1 flex gap-2">
        <span class="mt-[1px] shrink-0 text-[12px] font-semibold text-indigo-500">{{ row.n }}.</span>
        <p class="min-w-0 flex-1">
          <template v-for="(seg, j) in row.inlines[0]" :key="j">
            <strong v-if="seg.t === 'b'" class="font-semibold text-zinc-800">{{ seg.s }}</strong>
            <code v-else-if="seg.t === 'code'" class="rounded bg-zinc-100 px-1 font-mono text-[12px]">{{ seg.s }}</code>
            <span v-else>{{ seg.s }}</span>
          </template>
        </p>
      </div>
      <blockquote v-else-if="row.kind === 'quote'" class="my-1.5 rounded-r-lg border-l-[3px] border-zinc-300 bg-zinc-50 px-3 py-1.5 text-[12.5px] text-zinc-500">
        <template v-for="(seg, j) in row.inlines[0]" :key="j">
          <strong v-if="seg.t === 'b'" class="font-semibold text-zinc-700">{{ seg.s }}</strong>
          <code v-else-if="seg.t === 'code'" class="rounded bg-zinc-200/70 px-1 font-mono text-[12px]">{{ seg.s }}</code>
          <span v-else>{{ seg.s }}</span>
        </template>
      </blockquote>
      <pre v-else-if="row.kind === 'code'" class="my-2 overflow-x-auto rounded-lg bg-zinc-900 px-3.5 py-2.5 font-mono text-[12px] leading-relaxed text-zinc-100">{{ row.code }}</pre>
      <hr v-else class="my-3 border-zinc-100" />
    </template>
  </div>
</template>
