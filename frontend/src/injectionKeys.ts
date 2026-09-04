import type { InjectionKey } from 'vue'

/** 打开 AI 设置弹窗（由 AppShell 提供，弹窗等处注入使用） */
export const OPEN_AI_SETTINGS: InjectionKey<() => void> = Symbol('OpenAiSettings')

/** 跳转到岗位跟踪并按关键字过滤（由 AppShell 提供；q 为公司名等搜索词） */
export const FOCUS_BOARD: InjectionKey<(q?: string) => void> = Symbol('FocusBoard')

/** 打开简历详情页（由 AppShell 提供，参数为简历 id） */
export const OPEN_RESUME_DETAIL: InjectionKey<(id: number) => void> = Symbol(
  'OpenResumeDetail',
)

/** 打开岗位详情页（由 AppShell 提供，参数为岗位 id） */
export const OPEN_OPPORTUNITY_DETAIL: InjectionKey<(id: number) => void> = Symbol(
  'OpenOpportunityDetail',
)
