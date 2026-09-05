import type {
  MatchReportInfo,
  MockInterviewInfo,
  Opportunity,
  PredictionInfo,
  Question,
  ResearchMaterial,
  ResearchNote,
  Resume,
  RoundEvent,
} from './types'
import { clearAuthUser } from './composables/useAuth'

const BASE = '/api'

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const res = await fetch(BASE + path, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  })
  if (res.status === 401 && !path.startsWith('/auth/')) {
    // 会话失效：清掉本地登录态，前端自动切回登录页
    clearAuthUser()
  }
  if (!res.ok) {
    const body = await res.json().catch(() => ({}))
    throw new Error((body as { detail?: string }).detail ?? `请求失败 (${res.status})`)
  }
  return res.json() as Promise<T>
}

async function upload<T>(path: string, form: FormData): Promise<T> {
  const res = await fetch(BASE + path, { method: 'POST', body: form })
  if (res.status === 401 && !path.startsWith('/auth/')) {
    clearAuthUser()
  }
  if (!res.ok) {
    const body = await res.json().catch(() => ({}))
    throw new Error((body as { detail?: string }).detail ?? `上传失败 (${res.status})`)
  }
  return res.json() as Promise<T>
}

export interface OpportunityPayload {
  company: string
  position: string
  department: string | null
  city: string | null
  address: string | null
  salary_range: string | null
  channel: string | null
  priority: string
  status: string
  applied_at: string | null
  resume_id: number | null
  jd_text: string | null
  note: string | null
}

export interface AiSettingsInfo {
  base_url: string
  model: string
  api_key_configured: boolean
  api_key_masked: string | null
}

export interface AuthUser {
  id: number
  username: string
  display_name: string | null
  role: 'admin' | 'user'
  status: string
  avatar_url: string | null
  created_at: string | null
}

export interface ManagedUser {
  id: number
  username: string
  display_name: string | null
  role: 'admin' | 'user'
  status: 'active' | 'pending' | 'rejected' | 'disabled'
  reject_reason: string | null
  has_avatar: boolean
  created_at: string | null
  approved_at: string | null
  last_login_at: string | null
}

export interface NotificationItem {
  id: number
  type: string
  title: string
  body: string | null
  read: boolean
  created_at: string | null
}

export interface AuditLogItem {
  id: number
  user_id: number | null
  username: string
  action: string
  target: string | null
  detail: string | null
  ip: string | null
  created_at: string | null
}

export interface AuditLogPage {
  items: AuditLogItem[]
  total: number
  usernames: string[]
}

export interface InterviewReminder {
  round_id: number
  opportunity_id: number
  company: string
  position: string
  round_type: string
  scheduled_at: string
  day_label: string
  time_text: string
  note: string | null
  is_past: boolean
  pending: boolean
}

export interface NotificationSummary {
  unread_count: number
  items: NotificationItem[]
  interview_reminders: InterviewReminder[]
}

export interface AiSettingsUpdate {
  base_url?: string
  model?: string
  api_key?: string
}

export interface BrowserSettingsInfo {
  cdp_endpoint: string
}

export interface KnowledgeBaseInfo {
  path: string
  exists: boolean
  file_count: number
}

export interface ExtractedJobFields {
  company: string | null
  position: string | null
  department: string | null
  city: string | null
  address: string | null
  salary_range: string | null
  jd_text: string | null
  channel?: string | null
}

export interface QuestionSourceIn {
  opportunity_id: number
  round_id: number | null
}

export interface MockAnswerOrigin {
  mock_interview_id: number
  company: string | null
  position: string | null
  round_type: string
  created_at: string | null
  overall_score: number
  question: string
  my_answer: string | null
}

export interface RecordingAnswerOrigin {
  recording_id: number
  company: string | null
  round_type: string | null
  created_at: string | null
  question_text: string
  timestamp: string | null
  context_before: string | null
  my_answer: string | null
  excerpt: string | null
}

export interface QuestionOrigins {
  mock_answers: MockAnswerOrigin[]
  recording_answers: RecordingAnswerOrigin[]
}

export interface QuestionPayload {
  content: string
  dimension: string
  difficulty: string
  source: string
  opportunity_id: number | null
  resume_id: number | null
  sources: QuestionSourceIn[] | null
  my_answer: string | null
  answer_key: string | null
  answer_spoken: string | null
  self_rating: number | null
  mastery: string
}

export interface ResumeUpdatePayload {
  name?: string
  note?: string
  background?: string
}

export interface RoundPayload {
  opportunity_id: number
  round_type: string
  scheduled_at: string
  result: string
  note: string | null
}

export interface RecordingInfo {
  id: number
  opportunity_id: number
  round_id: number | null
  kind: string
  ext: string
  size: number
  duration_sec: number | null
  transcript: string | null
  transcript_clean: string | null
  polished_at: string | null
  polish_status: string
  polish_error: string | null
  transcript_engine: string | null
  status: string
  progress: number
  error: string | null
  review_status: string
  review_error: string | null
  created_at: string
  company: string | null
  position: string | null
  round_type: string | null
  round_scheduled_at: string | null
  review_score: number | null
  review_model: string | null
  review_created_at: string | null
}

export interface ReviewQuestion {
  question: string
  topic: string
  my_answer: string
  scores: { structure: number; depth: number; clarity: number }
  good: string[]
  bad: string[]
  reference: string
  improved: string
}

export interface ReviewReportData {
  overall: { score: number; summary: string; highlights: string[]; weaknesses: string[] }
  questions: ReviewQuestion[]
  jd_match: { demonstrated: string[]; gaps: string[] }
  interviewer_focus: string
  action_items: string[]
  questions_for_bank: { content: string; dimension: string; difficulty: string }[]
}

export interface ReviewReportInfo {
  id: number
  recording_id: number
  model: string
  overall_score: number
  question_count: number
  report: ReviewReportData
  created_at: string
}

export interface RecordingDetail extends RecordingInfo {
  review: ReviewReportInfo | null
}

export interface AsrSettingsInfo {
  provider: string
  whisper_model: string
  cloud_base_url: string
  cloud_model: string
  cloud_api_key_configured: boolean
  cloud_api_key_masked: string | null
}

export interface AsrSettingsUpdate {
  provider?: string
  whisper_model?: string
  cloud_base_url?: string
  cloud_model?: string
  cloud_api_key?: string
}

export interface OfferInfo {
  id: number
  opportunity_id: number
  company: string | null
  position: string | null
  city: string | null
  status: string | null
  salary_range: string | null
  monthly_salary: number | null
  months: number | null
  signing_bonus: string | null
  stock: string | null
  welfare: string | null
  overtime: string | null
  commute: string | null
  score_salary: number
  score_platform: number
  score_growth: number
  score_worklife: number
  score_commute: number
  note: string | null
}

export interface OfferPayload {
  monthly_salary: number | null
  months: number | null
  signing_bonus: string | null
  stock: string | null
  welfare: string | null
  overtime: string | null
  commute: string | null
  score_salary: number
  score_platform: number
  score_growth: number
  score_worklife: number
  score_commute: number
  note: string | null
}

export interface StatsOverview {
  funnel: { key: string; label: string; count: number }[]
  by_status: Record<string, number>
  channels: { channel: string; total: number; interviewed: number; offers: number }[]
  weekly: { week: string; applied: number; interviews: number }[]
  rounds: {
    round_type: string
    total: number
    passed: number
    failed: number
    no_show: number
    pass_rate: number | null
  }[]
  cycles: {
    apply_to_interview_days: number | null
    apply_to_offer_days: number | null
    response_rate: number | null
    responded: number
    no_response: number
    waiting: number
  }
  review_trend: { date: string; score: number; company: string | null }[]
  generated_at: string
}

export interface DashboardUpcoming {
  round_id: number
  opportunity_id: number
  company: string
  position: string
  round_type: string
  scheduled_at: string
}

export interface DashboardData {
  generated_at: string
  cards: {
    active_opportunities: number
    upcoming_interviews: number
    applied_week: number
    offers: number
    questions_total: number
    questions_todo: number
    resumes: number
    resume_best_score: number | null
    recordings: number
    recordings_todo: number
    review_avg_score: number | null
    interviews_done: number
    interview_pass_rate: number | null
  }
  upcoming: DashboardUpcoming[]
  todos: {
    round_results: { opportunity_id: number; company: string; round_type: string; scheduled_at: string }[]
    round_results_total: number
    overdue_wishlist: { opportunity_id: number; company: string; position: string; days: number }[]
    overdue_total: number
    missing_jd: { opportunity_id: number; company: string; position: string }[]
    missing_jd_total: number
    questions_todo: number
    recordings_review: { id: number; company: string | null; title: string; created_at: string }[]
    recordings_total: number
    resumes_no_review: { id: number; name: string }[]
    resumes_total: number
  }
  activity: { ts: string; kind: string; text: string; opportunity_id: number | null }[]
  funnel: { key: string; label: string; count: number }[]
}

export const api = {
  listOpportunities: () =>
    request<{ items: Opportunity[]; total: number }>('/opportunities'),

  createOpportunity: (payload: OpportunityPayload) =>
    request<Opportunity>('/opportunities', { method: 'POST', body: JSON.stringify(payload) }),

  updateOpportunity: (id: number, payload: Partial<OpportunityPayload>) =>
    request<Opportunity>(`/opportunities/${id}`, {
      method: 'PATCH',
      body: JSON.stringify(payload),
    }),

  deleteOpportunity: (id: number) =>
    request<{ ok: boolean }>(`/opportunities/${id}`, { method: 'DELETE' }),

  getAiSettings: () => request<AiSettingsInfo>('/settings/ai'),

  saveAiSettings: (payload: AiSettingsUpdate) =>
    request<AiSettingsInfo>('/settings/ai', { method: 'PUT', body: JSON.stringify(payload) }),

  getBrowserSettings: () => request<BrowserSettingsInfo>('/settings/browser'),

  saveBrowserSettings: (payload: { cdp_endpoint: string }) =>
    request<BrowserSettingsInfo>('/settings/browser', {
      method: 'PUT',
      body: JSON.stringify(payload),
    }),

  getKbSettings: () => request<KnowledgeBaseInfo>('/settings/kb'),

  saveKbSettings: (payload: { path: string }) =>
    request<KnowledgeBaseInfo>('/settings/kb', {
      method: 'PUT',
      body: JSON.stringify(payload),
    }),

  extractJob: (payload: { url?: string; text?: string; active_tab?: boolean }) =>
    request<{ fields: ExtractedJobFields; source: string }>('/ai/extract-job', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),

  // ---- 面试日历 / 轮次 ----

  calendarEvents: (start: string, end: string) =>
    request<{ events: RoundEvent[]; total: number }>(
      `/calendar/events?start=${start}&end=${end}`,
    ),

  createRound: (payload: RoundPayload) =>
    request<RoundEvent>('/rounds', { method: 'POST', body: JSON.stringify(payload) }),

  updateRound: (id: number, payload: Partial<RoundPayload>) =>
    request<RoundEvent>(`/rounds/${id}`, {
      method: 'PATCH',
      body: JSON.stringify(payload),
    }),

  deleteRound: (id: number) =>
    request<{ ok: boolean }>(`/rounds/${id}`, { method: 'DELETE' }),

  // ---- 题库 / 错题本 ----

  listQuestions: () => request<{ items: Question[]; total: number }>('/questions'),

  questionMeta: () => request<{ dimensions: string[] }>('/questions/meta'),

  createQuestion: (payload: QuestionPayload) =>
    request<Question>('/questions', { method: 'POST', body: JSON.stringify(payload) }),

  updateQuestion: (id: number, payload: Partial<QuestionPayload> & { review_done?: boolean }) =>
    request<Question>(`/questions/${id}`, {
      method: 'PATCH',
      body: JSON.stringify(payload),
    }),

  deleteQuestion: (id: number) =>
    request<{ ok: boolean }>(`/questions/${id}`, { method: 'DELETE' }),

  questionOrigins: (id: number) =>
    request<QuestionOrigins>(`/questions/${id}/origins`),

  // ---- 简历库 ----

  listResumes: () => request<{ items: Resume[]; total: number }>('/resumes'),

  uploadResume: (file: File, name?: string) => {
    const fd = new FormData()
    fd.append('file', file)
    if (name) fd.append('name', name)
    return upload<Resume>('/resumes', fd)
  },

  updateResume: (id: number, payload: ResumeUpdatePayload) =>
    request<Resume>(`/resumes/${id}`, {
      method: 'PATCH',
      body: JSON.stringify(payload),
    }),

  deleteResume: (id: number) =>
    request<{ ok: boolean }>(`/resumes/${id}`, { method: 'DELETE' }),

  setDefaultResume: (id: number) =>
    request<{ ok: boolean; default_id: number }>(`/resumes/${id}/set-default`, {
      method: 'POST',
    }),

  structureResume: (id: number) =>
    request<Resume>(`/resumes/${id}/structure`, { method: 'POST' }),

  reviewResume: (id: number) =>
    request<Resume>(`/resumes/${id}/review`, { method: 'POST' }),

  predictResumeQuestions: (id: number, direction?: string) =>
    request<Resume>(`/resumes/${id}/predict-questions`, {
      method: 'POST',
      body: JSON.stringify({ direction: direction?.trim() || null }),
    }),

  resumeFileUrl: (id: number) => `${BASE}/resumes/${id}/file`,

  // ---- Offer 对比 ----

  listOffers: () => request<{ items: OfferInfo[] }>('/offers'),

  upsertOffer: (opportunityId: number, payload: OfferPayload) =>
    request<OfferInfo>(`/offers/${opportunityId}`, {
      method: 'PUT',
      body: JSON.stringify(payload),
    }),

  deleteOffer: (opportunityId: number) =>
    request<{ ok: boolean }>(`/offers/${opportunityId}`, { method: 'DELETE' }),

  // ---- AI 答案生成 ----

  generateAnswer: (payload: {
    question_id?: number
    content?: string
    dimension?: string
    companies?: string[]
    opportunity_id?: number
    resume_id?: number
  }) =>
    request<{ answer_spoken: string | null; saved: boolean }>('/ai/generate-answer', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),

  // ---- 题目录入 AI 辅助（润色题干 / 选考察维度） ----

  questionAssist: (payload: { content: string; dimensions: string[]; task?: 'polish' | 'dimension' }) =>
    request<{ content?: string; dimension: string }>('/ai/question-assist', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),

  // ---- 统计 ----

  statsOverview: () => request<StatsOverview>('/stats/overview'),

  statsDashboard: () => request<DashboardData>('/stats/dashboard'),

  // ---- 录音复盘 ----

  listRecordings: () => request<{ items: RecordingInfo[]; total: number }>('/recordings'),

  getRecording: (id: number) => request<RecordingDetail>(`/recordings/${id}`),

  uploadRecording: (file: File, opportunityId: number, roundId: number | null) => {
    const fd = new FormData()
    fd.append('file', file)
    fd.append('opportunity_id', String(opportunityId))
    if (roundId != null) fd.append('round_id', String(roundId))
    return upload<RecordingInfo>('/recordings', fd)
  },

  deleteRecording: (id: number) =>
    request<{ ok: boolean }>(`/recordings/${id}`, { method: 'DELETE' }),

  recordingFileUrl: (id: number) => `${BASE}/recordings/${id}/file`,

  createTextRecording: (payload: { opportunity_id: number; round_id: number | null; title: string | null; transcript: string }) =>
    request<RecordingInfo>('/recordings/text', { method: 'POST', body: JSON.stringify(payload) }),

  transcribeRecording: (id: number, engine: 'local' | 'cloud') =>
    request<{ ok: boolean }>(`/recordings/${id}/transcribe`, {
      method: 'POST',
      body: JSON.stringify({ engine }),
    }),

  saveTranscript: (id: number, transcript: string, target: 'raw' | 'clean' = 'raw') =>
    request<RecordingInfo>(`/recordings/${id}/transcript`, {
      method: 'PUT',
      body: JSON.stringify({ transcript, target }),
    }),

  polishRecording: (id: number) =>
    request<{ ok: boolean }>(`/recordings/${id}/polish`, { method: 'POST' }),

  generateReview: (id: number, resumeId: number | null) =>
    request<{ ok: boolean }>(`/recordings/${id}/review`, {
      method: 'POST',
      body: JSON.stringify({ resume_id: resumeId }),
    }),

  // ---- 转写（ASR）设置 ----

  getAsrSettings: () => request<AsrSettingsInfo>('/settings/asr'),

  saveAsrSettings: (payload: AsrSettingsUpdate) =>
    request<AsrSettingsInfo>('/settings/asr', {
      method: 'PUT',
      body: JSON.stringify(payload),
    }),

  // ---- 岗位详情：调研笔记 / 匹配度报告 ----

  listNotes: (opportunityId: number) =>
    request<{ items: ResearchNote[] }>(`/opportunities/${opportunityId}/notes`),

  saveNote: (opportunityId: number, noteType: string, payload: { content: string; ai_generated: boolean }) =>
    request<ResearchNote>(`/opportunities/${opportunityId}/notes/${noteType}`, {
      method: 'PUT',
      body: JSON.stringify(payload),
    }),

  deleteNote: (opportunityId: number, noteType: string) =>
    request<{ ok: boolean }>(`/opportunities/${opportunityId}/notes/${noteType}`, {
      method: 'DELETE',
    }),

  listMaterials: (opportunityId: number) =>
    request<{ items: ResearchMaterial[] }>(`/opportunities/${opportunityId}/materials`),

  addMaterials: (
    opportunityId: number,
    payload: { urls: string[]; manual_text: string; manual_title: string },
  ) =>
    request<{
      saved: ResearchMaterial[]
      failed: { url: string; error: string }[]
      duplicates: string[]
    }>(`/opportunities/${opportunityId}/materials`, {
      method: 'POST',
      body: JSON.stringify(payload),
    }),

  deleteMaterial: (opportunityId: number, materialId: number) =>
    request<{ ok: boolean }>(`/opportunities/${opportunityId}/materials/${materialId}`, {
      method: 'DELETE',
    }),

  autoResearch: (opportunityId: number) =>
    request<{
      saved: ResearchMaterial[]
      failed: { source: string; error: string }[]
      duplicates: string[]
    }>(`/opportunities/${opportunityId}/notes/auto-research`, { method: 'POST' }),

  generateOutline: (opportunityId: number, noteType: string, overwrite: boolean) =>
    request<ResearchNote>(`/opportunities/${opportunityId}/notes/${noteType}/outline`, {
      method: 'POST',
      body: JSON.stringify({ overwrite }),
    }),

  getMatchReport: (opportunityId: number) =>
    request<{ report: MatchReportInfo | null }>(
      `/opportunities/${opportunityId}/match-report`,
    ),

  generateMatchReport: (opportunityId: number, resumeId: number | null) =>
    request<MatchReportInfo>(`/opportunities/${opportunityId}/match-report`, {
      method: 'POST',
      body: JSON.stringify({ resume_id: resumeId }),
    }),

  deleteMatchReport: (opportunityId: number) =>
    request<{ ok: boolean }>(`/opportunities/${opportunityId}/match-report`, {
      method: 'DELETE',
    }),

  // ---- 题目预测 / 模拟面试 ----

  listPredictions: (opportunityId: number) =>
    request<{ items: PredictionInfo[] }>(`/opportunities/${opportunityId}/predictions`),

  generatePrediction: (opportunityId: number, roundType: string) =>
    request<PredictionInfo>(`/opportunities/${opportunityId}/predictions`, {
      method: 'POST',
      body: JSON.stringify({ round_type: roundType }),
    }),

  deletePrediction: (opportunityId: number, predictionId: number) =>
    request<{ ok: boolean }>(`/opportunities/${opportunityId}/predictions/${predictionId}`, {
      method: 'DELETE',
    }),

  listMockInterviews: (opportunityId: number) =>
    request<{ items: MockInterviewInfo[] }>(`/opportunities/${opportunityId}/mock-interviews`),

  createMockInterview: (opportunityId: number, roundType: string) =>
    request<MockInterviewInfo>(`/opportunities/${opportunityId}/mock-interviews`, {
      method: 'POST',
      body: JSON.stringify({ round_type: roundType }),
    }),

  replyMockInterview: (interviewId: number, content: string, kind: 'answer' | 'skip' = 'answer') =>
    request<MockInterviewInfo>(`/mock-interviews/${interviewId}/reply`, {
      method: 'POST',
      body: JSON.stringify({ content, kind }),
    }),

  finishMockInterview: (interviewId: number) =>
    request<MockInterviewInfo>(`/mock-interviews/${interviewId}/finish`, { method: 'POST' }),

  reanalyzeMockInterview: (interviewId: number) =>
    request<MockInterviewInfo>(`/mock-interviews/${interviewId}/reanalyze`, { method: 'POST' }),

  deleteMockInterview: (interviewId: number) =>
    request<{ ok: boolean }>(`/mock-interviews/${interviewId}`, { method: 'DELETE' }),

  // ---- 认证 / 用户 ----

  registerStatus: () => request<{ enabled: boolean }>('/auth/register-status'),

  updateProfile: (payload: { display_name?: string }) =>
    request<AuthUser>('/auth/me', { method: 'PUT', body: JSON.stringify(payload) }),

  updatePassword: (payload: { old_password: string; new_password: string }) =>
    request<{ ok: boolean }>('/auth/me/password', {
      method: 'PUT',
      body: JSON.stringify(payload),
    }),

  uploadAvatar: (file: File) => {
    const fd = new FormData()
    fd.append('file', file)
    return upload<AuthUser>('/auth/me/avatar', fd)
  },

  deleteAvatar: () => request<AuthUser>('/auth/me/avatar', { method: 'DELETE' }),

  listUsers: () => request<ManagedUser[]>('/users'),

  createUser: (payload: { username: string; password: string; display_name?: string; role?: string }) =>
    request<ManagedUser>('/users', { method: 'POST', body: JSON.stringify(payload) }),

  approveUser: (id: number) =>
    request<ManagedUser>(`/users/${id}/approve`, { method: 'POST' }),

  rejectUser: (id: number, reason: string) =>
    request<ManagedUser>(`/users/${id}/reject`, {
      method: 'POST',
      body: JSON.stringify({ reason }),
    }),

  disableUser: (id: number) =>
    request<ManagedUser>(`/users/${id}/disable`, { method: 'POST' }),

  enableUser: (id: number) =>
    request<ManagedUser>(`/users/${id}/enable`, { method: 'POST' }),

  resetUserPassword: (id: number, newPassword: string) =>
    request<{ ok: boolean }>(`/users/${id}/password`, {
      method: 'POST',
      body: JSON.stringify({ new_password: newPassword }),
    }),

  deleteUser: (id: number) =>
    request<{ ok: boolean }>(`/users/${id}`, { method: 'DELETE' }),

  userAvatarUrl: (id: number) => `${BASE}/users/${id}/avatar`,

  // ---- 操作日志（仅管理员） ----

  listAuditLogs: (params: { category?: string; username?: string; limit?: number; offset?: number } = {}) => {
    const q = new URLSearchParams()
    if (params.category) q.set('category', params.category)
    if (params.username) q.set('username', params.username)
    q.set('limit', String(params.limit ?? 50))
    q.set('offset', String(params.offset ?? 0))
    return request<AuditLogPage>(`/audit-logs?${q.toString()}`)
  },

  // ---- 系统设置（注册开关） ----

  getRegistrationSettings: () =>
    request<{ enabled: boolean }>('/settings/registration'),

  saveRegistrationSettings: (enabled: boolean) =>
    request<{ enabled: boolean }>('/settings/registration', {
      method: 'PUT',
      body: JSON.stringify({ enabled }),
    }),

  // ---- 通知 ----

  notificationSummary: () => request<NotificationSummary>('/notifications/summary'),

  markNotificationsRead: (ids?: number[]) =>
    request<{ updated: number }>('/notifications/read', {
      method: 'POST',
      body: JSON.stringify({ ids: ids ?? null }),
    }),

  deleteNotification: (id: number) =>
    request<{ ok: boolean }>(`/notifications/${id}`, { method: 'DELETE' }),
}
