/** Courses saved on the device so lessons can be read, and finished, without a connection. */
import type { Bi } from './helpers'

export interface CachedCourse {
  code: string
  level: 'basic' | 'advanced' | 'program'
  title: Bi
  languages: string[]
  lessons: { id: string; title: Bi; body: Bi }[]
  quiz: { count: number; pass_mark: number }
  lessons_done: string[]
  last_lesson: string | null
  completed: boolean
}

type Store = Pick<Storage, 'getItem' | 'setItem' | 'removeItem'>
const PREFIX = 'isd.course.'
const INDEX = 'isd.course.index'
export const MAX_SAVED_COURSES = 12

function read<T>(store: Store, key: string, fallback: T): T {
  try {
    const raw = store.getItem(key)
    return raw === null ? fallback : (JSON.parse(raw) as T)
  } catch {
    return fallback
  }
}

function write(store: Store, key: string, value: unknown) {
  try {
    store.setItem(key, JSON.stringify(value))
  } catch {
    // storage full or blocked: the course still works online
  }
}

export const loadCourse = (code: string, store: Store = localStorage): CachedCourse | null =>
  read<CachedCourse | null>(store, PREFIX + code, null)

export function saveCourse(course: CachedCourse, store: Store = localStorage) {
  const ids = [course.code, ...read<string[]>(store, INDEX, []).filter((c) => c !== course.code)]
  for (const old of ids.slice(MAX_SAVED_COURSES)) {
    try {
      store.removeItem(PREFIX + old)
    } catch {
      // ignore
    }
  }
  write(store, PREFIX + course.code, course)
  write(store, INDEX, ids.slice(0, MAX_SAVED_COURSES))
}

/** Lessons finished here (maybe offline) and on the server are both kept; progress never goes back. */
export function mergeCourse(local: CachedCourse | null, server: CachedCourse): CachedCourse {
  if (!local) return server
  const done = [...new Set([...server.lessons_done, ...local.lessons_done])]
  const order = server.lessons.map((l) => l.id)
  return {
    ...server,
    lessons_done: order.filter((id) => done.includes(id)),
    last_lesson: local.last_lesson ?? server.last_lesson,
    completed: server.completed || local.completed,
  }
}

export function markLessonDone(course: CachedCourse, lessonId: string): CachedCourse {
  if (course.lessons_done.includes(lessonId)) return { ...course, last_lesson: lessonId }
  const done = [...course.lessons_done, lessonId]
  const order = course.lessons.map((l) => l.id)
  return { ...course, lessons_done: order.filter((id) => done.includes(id)), last_lesson: lessonId }
}

/** The step to resume at: the first lesson not yet done, or the quiz when all are done. */
export function resumeStep(course: CachedCourse): number {
  if (course.completed) return course.lessons.length
  const first = course.lessons.findIndex((l) => !course.lessons_done.includes(l.id))
  return first === -1 ? course.lessons.length : first
}

export const featureForLevel = (level: CachedCourse['level']): string =>
  level === 'basic' ? 'basic_education' : 'advanced_education'
