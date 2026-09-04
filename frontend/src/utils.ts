/** 把 ISO 时间格式化为「今天 14:00」「明天 10:30」「9月12日 15:00」这类友好文案 */
export function eventLabel(dt: string | null): string | null {
  if (!dt) return null
  const d = new Date(dt)
  const now = new Date()
  const startToday = new Date(now.getFullYear(), now.getMonth(), now.getDate())
  const startDay = new Date(d.getFullYear(), d.getMonth(), d.getDate())
  const diff = Math.round((startDay.getTime() - startToday.getTime()) / 86400000)
  const hm = `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`
  if (diff === 0) return `今天 ${hm}`
  if (diff === 1) return `明天 ${hm}`
  if (diff === 2) return `后天 ${hm}`
  if (diff === -1) return `昨天`
  return `${d.getMonth() + 1}月${d.getDate()}日 ${hm}`
}

/** 紧凑日期：用于卡片/表格单元格，如 8/30 */
export function shortDate(dt: string | null): string | null {
  if (!dt) return null
  const d = new Date(dt)
  return `${d.getMonth() + 1}/${d.getDate()}`
}

/** Date → YYYY-MM-DD */
export function ymd(d: Date): string {
  const p = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`
}

/** 所在周的周一 0 点 */
export function startOfWeek(d: Date): Date {
  const diff = (d.getDay() + 6) % 7
  return new Date(d.getFullYear(), d.getMonth(), d.getDate() - diff)
}

/** 加 N 天（保留时分秒） */
export function addDays(d: Date, n: number): Date {
  return new Date(d.getFullYear(), d.getMonth(), d.getDate() + n)
}

/** HH:MM */
export function hm(dt: string | Date): string {
  const d = typeof dt === 'string' ? new Date(dt) : dt
  return `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`
}

/** 转为不带时区后缀的本地 ISO 串（与后端存储格式一致） */
export function toLocalIso(d: Date): string {
  const p = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}T${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}`
}

/** 距今多少天（向下取整，最小 0） */
export function daysSince(dt: string): number {
  return Math.max(0, Math.floor((Date.now() - new Date(dt).getTime()) / 86400000))
}

/** 距离目标日期还有几天（按自然日计算） */
export function daysUntil(dt: string | null): number | null {
  if (!dt) return null
  const d = new Date(dt)
  const startToday = new Date()
  startToday.setHours(0, 0, 0, 0)
  const startDay = new Date(d.getFullYear(), d.getMonth(), d.getDate())
  return Math.round((startDay.getTime() - startToday.getTime()) / 86400000)
}
