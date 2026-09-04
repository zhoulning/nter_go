export interface RoundInfo {
  id: number
  round_type: string
  scheduled_at: string | null
  actual_at: string | null
  result: string
  note: string | null
}

export interface Opportunity {
  id: number
  company: string
  position: string
  department: string | null
  city: string | null
  address: string | null
  salary_range: string | null
  channel: string | null
  priority: string
  status: string
  status_changed_at: string
  applied_at: string | null
  resume_id: number | null
  resume: { id: number; name: string; filename: string; ext: string; is_default: boolean } | null
  jd_text: string | null
  note: string | null
  created_at: string
  updated_at: string
  rounds: RoundInfo[]
  next_event: RoundInfo | null
}

export interface StatusMeta {
  key: string
  label: string
  color: string
}

/** 看板列（与后端 ACTIVE_STATUSES 对应；社招笔试场景少，按轮次记录而非独立状态） */
export const STATUSES: StatusMeta[] = [
  { key: 'wishlist', label: '想投', color: '#94a3b8' },
  { key: 'applied', label: '已投递', color: '#3b82f6' },
  { key: 'interviewing', label: '面试中', color: '#f59e0b' },
  { key: 'offer', label: 'Offer', color: '#10b981' },
  { key: 'accepted', label: '接受', color: '#14b8a6' },
]

export function statusLabel(key: string): string {
  return STATUSES.find((s) => s.key === key)?.label ?? key
}

export const PRIORITY_CLASS: Record<string, string> = {
  S: 'border-rose-200 bg-rose-50 text-rose-600',
  A: 'border-amber-200 bg-amber-50 text-amber-600',
  B: 'border-zinc-200 bg-zinc-50 text-zinc-500',
}

export const ROUND_LABEL: Record<string, string> = {
  written: '笔试',
  first: '一面',
  second: '二面',
  third: '三面',
  cross: '交叉面',
  hr: 'HR面',
  other: '面试',
}

export const CHANNELS = ['内推', 'BOSS直聘', '猎聘', '智联招聘', '官网', '脉脉', '其他']

// ---- 面试轮次 / 日历 ----

export interface RoundEvent extends RoundInfo {
  opportunity_id: number
  company: string
  position: string
}

export const ROUND_RESULT_META: Record<string, { label: string; color: string }> = {
  pending: { label: '待定', color: '#f59e0b' },
  passed: { label: '通过', color: '#10b981' },
  failed: { label: '挂了', color: '#ef4444' },
  no_show: { label: '未参加', color: '#94a3b8' },
}

// ---- 题库 / 错题本 ----

export interface QuestionSourceRef {
  opportunity_id: number
  round_id: number | null
  company: string | null
  position: string | null
  round_type: string | null
}

export interface Question {
  id: number
  content: string
  dimension: string
  difficulty: string
  source: string
  opportunity_id: number | null
  opportunity: { id: number; company: string; position: string } | null
  resume_id: number | null
  resume_name: string | null
  sources: QuestionSourceRef[]
  my_answer: string | null
  answer_key: string | null
  answer_spoken: string | null
  self_rating: number | null
  mastery: string
  review_done: boolean
  created_at: string
  updated_at: string
}

export const DIMENSION_PRESETS = [
  '语言特性',
  '并发编程',
  'JVM',
  'MySQL',
  'Redis',
  '消息队列',
  '分布式',
  '微服务',
  '计算机网络',
  '系统设计',
  '项目深挖',
  '场景设计',
  '算法',
  '软素质',
  '其他',
]

export const MASTERY_META: Record<string, { label: string; class: string }> = {
  unknown: { label: '不会', class: 'bg-rose-50 text-rose-600 border-rose-200' },
  fuzzy: { label: '模糊', class: 'bg-amber-50 text-amber-600 border-amber-200' },
  mastered: { label: '已掌握', class: 'bg-emerald-50 text-emerald-600 border-emerald-200' },
}

export const DIFFICULTY_META: Record<string, { label: string; class: string }> = {
  easy: { label: '简单', class: 'bg-emerald-50 text-emerald-600' },
  medium: { label: '中等', class: 'bg-amber-50 text-amber-600' },
  hard: { label: '困难', class: 'bg-rose-50 text-rose-600' },
}

export const QUESTION_SOURCE_LABEL: Record<string, string> = {
  manual: '手动添加',
  real: '真实面试',
  predicted: 'AI 预测',
}

// ---- 简历库 ----

export interface Resume {
  id: number
  name: string
  filename: string
  ext: string
  size: number
  text: string | null
  structured: string | null
  background: string | null
  score: number | null
  review_json: string | null
  questions_json: string | null
  is_default: boolean
  note: string | null
  created_at: string
}

export interface ResumeSuggestion {
  title: string
  detail: string
  level: 'high' | 'mid' | 'low'
}

export interface ResumePredictedQuestion {
  tag: string
  q: string
  a: string
}

export function parseResumeSuggestions(r: Resume | null): ResumeSuggestion[] {
  if (!r?.review_json) return []
  try {
    return (JSON.parse(r.review_json).suggestions ?? []) as ResumeSuggestion[]
  } catch {
    return []
  }
}

export function parseResumeQuestions(r: Resume | null): ResumePredictedQuestion[] {
  if (!r?.questions_json) return []
  try {
    return (JSON.parse(r.questions_json).questions ?? []) as ResumePredictedQuestion[]
  } catch {
    return []
  }
}

export const AVATAR_GRADIENTS = [
  'linear-gradient(135deg,#6366f1,#8b5cf6)',
  'linear-gradient(135deg,#3b82f6,#06b6d4)',
  'linear-gradient(135deg,#0ea5e9,#22d3ee)',
  'linear-gradient(135deg,#10b981,#84cc16)',
  'linear-gradient(135deg,#f59e0b,#f97316)',
  'linear-gradient(135deg,#ef4444,#ec4899)',
  'linear-gradient(135deg,#14b8a6,#3b82f6)',
  'linear-gradient(135deg,#8b5cf6,#d946ef)',
]

/** 按公司名哈希取一个稳定的渐变色做头像背景 */
export function avatarGradient(name: string): string {
  let h = 0
  for (const ch of name) h = (h * 31 + ch.charCodeAt(0)) % 997
  return AVATAR_GRADIENTS[h % AVATAR_GRADIENTS.length]
}

// ---- Offer 对比 ----

/** Offer 评分维度（与后端 Offer 模型的 score_* 字段对应） */
export const OFFER_DIMS = [
  { key: 'score_salary', label: '薪资待遇' },
  { key: 'score_platform', label: '平台规模' },
  { key: 'score_growth', label: '成长空间' },
  { key: 'score_worklife', label: '工作生活' },
  { key: 'score_commute', label: '通勤便利' },
] as const

export type OfferDimKey = (typeof OFFER_DIMS)[number]['key']

/** 默认权重（0-5，可调，存于浏览器本地） */
export const DEFAULT_OFFER_WEIGHTS: Record<OfferDimKey, number> = {
  score_salary: 5,
  score_platform: 3,
  score_growth: 4,
  score_worklife: 3,
  score_commute: 2,
}

/** 图表通用字体 */
export const CHART_FONT = "Inter, 'Noto Sans SC', 'Microsoft YaHei', sans-serif"

// ---- 岗位详情：调研笔记 / 匹配度报告 ----

export interface ResearchNote {
  id: number
  opportunity_id: number
  note_type: string
  content: string
  ai_generated: boolean
  updated_at: string | null
}

/** 调研笔记五大板块（与后端 NOTE_TYPES 对应） */
export const NOTE_TYPE_META: { key: string; label: string; hint: string }[] = [
  { key: 'company', label: '公司调研', hint: '业务、规模、竞品与口碑' },
  { key: 'team', label: '团队与业务', hint: '部门定位、技术栈、业务挑战' },
  { key: 'tech', label: '技术栈调研', hint: 'JD 技术关键词逐项复习' },
  { key: 'self_intro', label: '自我介绍稿', hint: '按这家公司定制的 1/3 分钟版' },
  { key: 'ask_back', label: '反问清单', hint: '体现做过功课的反问' },
]

export interface MatchItem {
  requirement: string
  weight: 'high' | 'mid' | 'low'
  verdict: 'match' | 'partial' | 'missing'
  evidence: string
  advice: string
}

export interface MatchReportData {
  job_profile: { hard: string[]; stack: string[]; soft: string[]; bonus: string[] }
  items: MatchItem[]
  total_score: number
  dimensions: Record<string, number>
  dimension_labels?: Record<string, string>
  focus: string[]
  resume_risks: string[]
}

export interface MatchReportInfo {
  id: number
  opportunity_id: number
  resume_id: number | null
  resume_name: string | null
  model: string
  total_score: number
  report: MatchReportData
  created_at: string
  company: string | null
  position: string | null
}

/** 匹配度五维（与后端 DIMENSIONS 对应，雷达图按此渲染） */
export const MATCH_DIMENSIONS = [
  { key: 'stack', label: '技术栈' },
  { key: 'experience', label: '经验' },
  { key: 'projects', label: '项目' },
  { key: 'soft', label: '软素质' },
  { key: 'fit', label: '发展契合' },
] as const

export const MATCH_VERDICT_META: Record<string, { label: string; class: string }> = {
  match: { label: '匹配', class: 'bg-emerald-50 text-emerald-600 border-emerald-200' },
  partial: { label: '部分匹配', class: 'bg-amber-50 text-amber-600 border-amber-200' },
  missing: { label: '缺失', class: 'bg-rose-50 text-rose-600 border-rose-200' },
}

export const MATCH_VERDICT_ICON: Record<string, string> = {
  match: '✅',
  partial: '⚠️',
  missing: '❌',
}

export const MATCH_WEIGHT_LABEL: Record<string, string> = { high: '高权重', mid: '中权重', low: '低权重' }

// ---- 题目预测 ----

export interface PredictedQuestion {
  group: string
  dimension: string
  q: string
  intent: string
  key_points: string
  difficulty: 'easy' | 'medium' | 'hard'
}

export interface PredictionReport {
  questions: PredictedQuestion[]
  weak_focus: string[]
  overall_advice: string
}

export interface PredictionInfo {
  id: number
  opportunity_id: number
  round_type: string
  model: string
  question_count: number
  report: PredictionReport | null
  created_at: string
}

/** 题单分组顺序（与后端 GROUPS 对应） */
export const PREDICT_GROUPS = ['八股基础', '项目深挖', '场景设计', '软素质', '反问建议'] as const

// ---- 模拟面试 ----

export interface MockTurn {
  role: 'interviewer' | 'candidate'
  content: string
  action: 'followup' | 'next' | 'finish' | null
  dimension: string | null
}

export interface MockAnalysisQuestion {
  question: string
  my_answer: string
  /** 跳过 / 结束时未回答的题不评分 */
  skipped?: boolean
  scores: { structure: number; depth: number; clarity: number } | null
  good: string[]
  bad: string[]
  reference: string
}

export interface MockAnalysis {
  overall: { score: number; summary: string }
  questions: MockAnalysisQuestion[]
  weak_dimensions: string[]
  action_items: string[]
  questions_for_bank: { content: string; dimension: string; difficulty: 'easy' | 'medium' | 'hard' }[]
}

export interface MockInterviewInfo {
  id: number
  opportunity_id: number
  round_type: string
  model: string
  status: 'ongoing' | 'finished'
  transcript: MockTurn[]
  analysis: MockAnalysis | null
  overall_score: number
  created_at: string
  finished_at: string | null
}
