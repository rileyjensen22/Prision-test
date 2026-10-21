import { useCallback, useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useParams, useNavigate } from 'react-router-dom'

import { NetworkError } from '../api'
import { BackLink, Card, reasonTitle } from '../components'
import { useResident } from '../ResidentContext'
import { L, errorCode } from './helpers'
import type { Bi } from './helpers'

interface CourseSummary {
  code: string
  level: 'basic' | 'advanced' | 'program'
  title: Bi
  lessons: number
  lessons_done: number
  completed: boolean
  allowed: boolean
  reasons: { code: string; params: Record<string, string | number> }[]
}

interface CourseDetail {
  code: string
  title: Bi
  lessons: { id: string; title: Bi; body: Bi }[]
  quiz: { id: string; prompt: Bi; choices: Bi[] }[]
  lessons_done: string[]
  completed: boolean
}

interface QuizResult {
  correct: number
  total: number
  passed: boolean
  points_awarded: number
  already_completed: boolean
  tier_before: number
  tier_after: number
  calls_minutes_before: number | null
  calls_minutes_after: number | null
}

export function Education() {
  const { t, i18n } = useTranslation()
  const { request, online } = useResident()
  const navigate = useNavigate()
  const [courses, setCourses] = useState<CourseSummary[] | null>(null)
  const [error, setError] = useState(false)

  useEffect(() => {
    request<CourseSummary[]>('/device/courses')
      .then(setCourses)
      .catch(() => setError(true))
  }, [request, online])

  return (
    <div className="space-y-6">
      <BackLink />
      <h1 className="text-3xl font-bold">{t('education.title')}</h1>
      {error && <p>{t('calls.needsConnection')}</p>}
      <ul className="space-y-4">
        {(courses ?? []).map((c) => (
          <li key={c.code}>
            <Card data-testid={`course-${c.code}`} data-allowed={c.allowed}>
              <p className="text-sm uppercase">{t(`education.${c.level}`)}</p>
              <h2 className="text-2xl font-semibold">{L(c.title, i18n.language)}</h2>
              <p>{t('education.progress', { done: c.lessons_done, total: c.lessons })}</p>
              {c.completed && <p data-testid="course-done">✓ {t('education.done')}</p>}
              {c.allowed ? (
                <button
                  onClick={() => navigate(`/resident/course/${c.code}`)}
                  className="mt-3 min-h-14 rounded-lg bg-blue-700 px-5 py-3 font-semibold"
                >
                  {c.completed
                    ? t('education.review')
                    : c.lessons_done
                      ? t('education.resume')
                      : t('education.start')}
                </button>
              ) : (
                <p data-testid="course-locked" className="mt-2">
                  🔒 {c.reasons[0] ? reasonTitle(t, c.reasons[0]) : t('education.lockedHint')}
                </p>
              )}
            </Card>
          </li>
        ))}
      </ul>
    </div>
  )
}

export function Course() {
  const { t, i18n } = useTranslation()
  const { code = '' } = useParams()
  const { request, refresh } = useResident()
  const lang = i18n.language
  const [course, setCourse] = useState<CourseDetail | null>(null)
  const [step, setStep] = useState(0) // 0..lessons-1, then lessons.length = quiz
  const [answers, setAnswers] = useState<Record<string, number>>({})
  const [result, setResult] = useState<QuizResult | null>(null)
  const [message, setMessage] = useState<string | null>(null)

  useEffect(() => {
    request<CourseDetail>(`/device/courses/${code}`)
      .then((c) => {
        setCourse(c)
        setStep(
          c.completed ? c.lessons.length : Math.min(c.lessons_done.length, c.lessons.length - 1),
        )
      })
      .catch((e) =>
        setMessage(
          e instanceof NetworkError ? t('calls.needsConnection') : t('education.lockedHint'),
        ),
      )
  }, [request, code, t])

  const next = useCallback(async () => {
    if (!course) return
    await request(`/device/courses/${code}/lessons/${course.lessons[step].id}/complete`, {
      method: 'POST',
    })
    setStep(step + 1)
  }, [course, request, code, step])

  async function submit() {
    if (!course) return
    try {
      const res = await request<QuizResult>(`/device/courses/${code}/quiz`, {
        method: 'POST',
        body: JSON.stringify({ answers: course.quiz.map((q) => answers[q.id]) }),
      })
      setResult(res)
      void refresh() // the home screen should show the new tier and call minutes
    } catch (e) {
      setMessage(e instanceof NetworkError ? t('calls.needsConnection') : errorCode(e))
    }
  }

  if (!course)
    return (
      <div className="space-y-6">
        <BackLink />
        {message && <p>{message}</p>}
      </div>
    )
  const onQuiz = step >= course.lessons.length

  return (
    <div className="space-y-6">
      <BackLink />
      <h1 className="text-3xl font-bold">{L(course.title, lang)}</h1>
      {result ? (
        <Card data-testid="quiz-result">
          <h2 className="text-3xl font-bold">
            {result.passed
              ? t('education.passed')
              : t('education.failed', { correct: result.correct, total: result.total })}
          </h2>
          {result.passed && (
            <p>{t('education.score', { correct: result.correct, total: result.total })}</p>
          )}
          {result.points_awarded > 0 && (
            <p data-testid="points-earned" className="text-2xl">
              {t('education.points', { n: result.points_awarded })}
            </p>
          )}
          {result.passed && result.already_completed && <p>{t('education.already')}</p>}
          {result.tier_after > result.tier_before && (
            <p data-testid="tier-up">
              {t('education.tierUp', { from: result.tier_before, to: result.tier_after })}
            </p>
          )}
          {result.calls_minutes_after != null &&
            result.calls_minutes_after !== result.calls_minutes_before && (
              <p data-testid="calls-up">
                {t('education.callsUp', {
                  from: result.calls_minutes_before,
                  to: result.calls_minutes_after,
                })}
              </p>
            )}
          {!result.passed && (
            <button
              className="mt-3 min-h-14 rounded-lg bg-blue-700 px-5 py-3"
              onClick={() => {
                setResult(null)
                setAnswers({})
                setStep(0)
              }}
            >
              {t('education.retry')}
            </button>
          )}
        </Card>
      ) : !onQuiz ? (
        <Card data-testid="lesson">
          <p className="text-sm">
            {t('education.lesson', { n: step + 1, total: course.lessons.length })}
          </p>
          <h2 className="text-2xl font-semibold">{L(course.lessons[step].title, lang)}</h2>
          <p className="mt-3">{L(course.lessons[step].body, lang)}</p>
          <button
            onClick={() => void next()}
            className="mt-4 min-h-14 rounded-lg bg-blue-700 px-5 py-3 font-semibold"
          >
            {step === course.lessons.length - 1 ? t('education.startQuiz') : t('education.next')}
          </button>
        </Card>
      ) : (
        <Card data-testid="quiz">
          <h2 className="text-2xl font-semibold">{t('education.quiz')}</h2>
          {course.quiz.map((q, qi) => (
            <fieldset key={q.id} className="mt-4" data-testid={`question-${qi}`}>
              <legend className="font-semibold">
                {qi + 1}. {L(q.prompt, lang)}
              </legend>
              {q.choices.map((c, ci) => (
                <label
                  key={ci}
                  className="mt-2 flex min-h-14 items-center gap-3 rounded-lg border-2 border-slate-500 px-4"
                >
                  <input
                    type="radio"
                    name={q.id}
                    checked={answers[q.id] === ci}
                    onChange={() => setAnswers({ ...answers, [q.id]: ci })}
                    className="h-6 w-6"
                  />
                  {L(c, lang)}
                </label>
              ))}
            </fieldset>
          ))}
          <button
            onClick={() => void submit()}
            disabled={course.quiz.some((q) => answers[q.id] === undefined)}
            className="mt-5 min-h-14 rounded-lg bg-blue-700 px-5 py-3 font-semibold disabled:opacity-40"
          >
            {t('education.submit')}
          </button>
          {message && <p role="alert">{message}</p>}
        </Card>
      )}
    </div>
  )
}
