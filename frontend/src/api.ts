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

const BASE = '/api'

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const res = await fetch(BASE + path, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  })
  if (!res.ok) {
    const body = await res.json().catch(() => ({}))
    throw new Error((body as { detail?: string }).detail ?? `请求失败 (${res.status})`)
  }
  return res.json() as Promise<T>
}

async function upload<T>(path: string, form: FormData): Promise<T> {
  const res = await fetch(BASE + path, { method: 'POST', body: form })
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

export interface AiSettingsUpdate {
  base_url?: string
  model?: string
  api_key?: string
}

export interface BrowserSettingsInfo {
  cdp_endpoint: string
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
  generated_at: string
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

  predictResumeQuestions: (id: number) =>
    request<Resume>(`/resumes/${id}/predict-questions`, { method: 'POST' }),

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
  }) =>
    request<{ answer_spoken: string | null; saved: boolean }>('/ai/generate-answer', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),

  // ---- 统计 ----

  statsOverview: () => request<StatsOverview>('/stats/overview'),

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
}
