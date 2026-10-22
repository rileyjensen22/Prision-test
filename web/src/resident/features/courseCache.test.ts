import { describe, expect, it } from 'vitest'

import {
  MAX_SAVED_COURSES,
  featureForLevel,
  loadCourse,
  markLessonDone,
  mergeCourse,
  resumeStep,
  saveCourse,
} from './courseCache'
import type { CachedCourse } from './courseCache'

function memory() {
  const m = new Map<string, string>()
  return {
    getItem: (k: string) => m.get(k) ?? null,
    setItem: (k: string, v: string) => void m.set(k, v),
    removeItem: (k: string) => void m.delete(k),
  }
}

const course = (code = 'NUM101', done: string[] = []): CachedCourse => ({
  code,
  level: 'basic',
  title: { en: code, es: code },
  languages: ['en'],
  lessons: ['a', 'b', 'c'].map((id) => ({
    id,
    title: { en: id, es: id },
    body: { en: id, es: id },
  })),
  quiz: { count: 4, pass_mark: 0.6 },
  lessons_done: done,
  last_lesson: done.at(-1) ?? null,
  completed: false,
})

describe('course cache', () => {
  it('round-trips and keeps only the most recent courses', () => {
    const store = memory()
    saveCourse(course('A1'), store)
    expect(loadCourse('A1', store)?.code).toBe('A1')
    for (let i = 0; i < MAX_SAVED_COURSES + 2; i++) saveCourse(course(`C${i}`), store)
    expect(loadCourse('A1', store)).toBeNull()
    expect(loadCourse(`C${MAX_SAVED_COURSES + 1}`, store)).not.toBeNull()
  })

  it('survives storage that throws', () => {
    const broken = {
      getItem: () => {
        throw new Error('blocked')
      },
      setItem: () => {
        throw new Error('blocked')
      },
      removeItem: () => {
        throw new Error('blocked')
      },
    }
    expect(() => saveCourse(course(), broken)).not.toThrow()
    expect(loadCourse('NUM101', broken)).toBeNull()
  })
})

describe('progress', () => {
  it('lessons done offline are kept when the server is behind, and never go backward', () => {
    const local = markLessonDone(markLessonDone(course(), 'a'), 'b')
    const merged = mergeCourse(local, course('NUM101', ['a']))
    expect(merged.lessons_done).toEqual(['a', 'b'])
    expect(mergeCourse(course('NUM101', ['a']), local).lessons_done).toEqual(['a', 'b'])
  })

  it('finishing a lesson twice changes nothing', () => {
    const once = markLessonDone(course(), 'a')
    expect(markLessonDone(once, 'a').lessons_done).toEqual(['a'])
  })

  it('resumes at the first lesson not finished, then at the quiz', () => {
    expect(resumeStep(course())).toBe(0)
    expect(resumeStep(course('NUM101', ['a', 'b']))).toBe(2)
    expect(resumeStep(course('NUM101', ['a', 'b', 'c']))).toBe(3)
    expect(resumeStep({ ...course(), completed: true })).toBe(3)
  })

  it('maps a course level to the entitlement that gates it', () => {
    expect(featureForLevel('basic')).toBe('basic_education')
    expect(featureForLevel('advanced')).toBe('advanced_education')
    expect(featureForLevel('program')).toBe('advanced_education')
  })
})
