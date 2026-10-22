import { useCallback, useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link, useNavigate, useParams } from 'react-router-dom'

import { NetworkError } from '../api'
import { BackLink, Card, reasonTitle } from '../components'
import { useResident } from '../ResidentContext'
import { loadCourse, markLessonDone, mergeCourse, resumeStep, saveCourse } from './courseCache'
import type { CachedCourse } from './courseCache'
import { L, errorCode } from './helpers'
import type { Bi } from './helpers'
import { Markdown } from './Markdown'

interface CourseSummary {
  code: string
  level: 'basic' | 'advanced' | 'program'
  title: Bi
  summary: Bi | null
  lessons: number
  lessons_done: number
  completed: boolean
  allowed: boolean
  missing: string[]
  missing_titles: Record<string, Bi>
  certificate: string | null
  reasons: { code: string; params: Record<string, string | number> }[]
}

interface QuizPaper {
  quiz_id: number
  questions: { id: string; prompt: Bi; choices: Bi[] }[]
  expires_at: string
  attempt_no: number
  attempts_left: number | null
}

interface QuizResult {
  correct: number
  total: number
  passed: boolean
  points_awarded: number
  already_completed: boolean
  certificate: string | null
  tier_before: number
  tier_after: number
  calls_minutes_before: number | null
  calls_minutes_after: number | null
  attempts?: { retry_at: string | null; attempts_left: number | null }
}

interface Pacing {
  code: string
  retry_at: string | null
}

export interface CertificateData {
  serial: string
  course: string
  title: Bi
  level: string
  score: string
  issued_at: string
  resident: string
}

const btn = 'mt-3 min-h-14 rounded-lg bg-blue-700 px-5 py-3 font-semibold'

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
      <Link to="/resident/certificates" className="block underline" data-testid="my-certificates">
        {t('education.myCertificates')}
      </Link>
      {error && <p>{t('calls.needsConnection')}</p>}
      <ul className="space-y-4">
        {(courses ?? []).map((c) => (
          <li key={c.code}>
            <Card data-testid={`course-${c.code}`} data-allowed={c.allowed}>
              <p className="text-sm uppercase">{t(`education.${c.level}`)}</p>
              <h2 className="text-2xl font-semibold">{L(c.title, i18n.language)}</h2>
              {c.summary && <p>{L(c.summary, i18n.language)}</p>}
              <p>{t('education.progress', { done: c.lessons_done, total: c.lessons })}</p>
              {c.completed && <p data-testid="course-done">✓ {t('education.done')}</p>}
              {c.certificate && (
                <Link to={`/resident/certificate/${c.certificate}`} className="underline">
                  {t('education.viewCertificate')}
                </Link>
              )}
              {c.allowed ? (
                <button onClick={() => navigate(`/resident/course/${c.code}`)} className={btn}>
                  {c.completed
                    ? t('education.review')
                    : c.lessons_done
                      ? t('education.resume')
                      : t('education.start')}
                </button>
              ) : (
                <div data-testid="course-locked" className="mt-2">
                  <p>
                    🔒 {c.reasons[0] ? reasonTitle(t, c.reasons[0]) : t('education.lockedHint')}
                  </p>
                  {c.missing.length > 0 && (
                    <p data-testid="course-missing">
                      {t('education.finishFirst', {
                        titles: c.missing
                          .map((m) => L(c.missing_titles[m], i18n.language) || m)
                          .join(', '),
                      })}
                    </p>
                  )}
                </div>
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
  const { request, refresh, submit } = useResident()
  const lang = i18n.language
  const [course, setCourse] = useState<CachedCourse | null>(null)
  const [step, setStep] = useState(0) // 0..lessons-1, then lessons.length = quiz
  const [paper, setPaper] = useState<QuizPaper | null>(null)
  const [answers, setAnswers] = useState<Record<string, number>>({})
  const [result, setResult] = useState<QuizResult | null>(null)
  const [pacing, setPacing] = useState<Pacing | null>(null)
  const [message, setMessage] = useState<string | null>(null)
  const [offlineCopy, setOfflineCopy] = useState(false)

  useEffect(() => {
    const local = loadCourse(code)
    request<CachedCourse>(`/device/courses/${code}`)
      .then((server) => {
        const merged = mergeCourse(local, server)
        saveCourse(merged)
        setCourse(merged)
        setOfflineCopy(false)
        setStep(resumeStep(merged))
      })
      .catch((e) => {
        if (e instanceof NetworkError && local) {
          setCourse(local)
          setOfflineCopy(true)
          setStep(resumeStep(local))
        } else
          setMessage(
            e instanceof NetworkError ? t('calls.needsConnection') : t('education.lockedHint'),
          )
      })
  }, [request, code, t])

  const next = useCallback(async () => {
    if (!course) return
    const lesson = course.lessons[step]
    // Saved here first, so finishing a lesson survives the connection dropping.
    const updated = markLessonDone(course, lesson.id)
    saveCourse(updated)
    setCourse(updated)
    setStep(step + 1)
    await submit({ type: 'lesson_complete', payload: { code, lesson_id: lesson.id } })
  }, [course, submit, code, step])

  async function startQuiz() {
    setMessage(null)
    setPacing(null)
    try {
      const p = await request<QuizPaper>(`/device/courses/${code}/quiz/start`, { method: 'POST' })
      setPaper(p)
      setAnswers({})
    } catch (e) {
      const detail = (e as { body?: { detail?: { code?: string; retry_at?: string | null } } })
        ?.body?.detail
      if (e instanceof NetworkError) setMessage(t('calls.needsConnection'))
      else if (detail?.code === 'COOLDOWN' || detail?.code === 'ATTEMPTS_EXHAUSTED')
        setPacing({ code: detail.code, retry_at: detail.retry_at ?? null })
      else
        setMessage(t(`education.err.${errorCode(e)}`, { defaultValue: t('education.err.ERROR') }))
    }
  }

  async function handIn() {
    if (!paper) return
    try {
      const res = await request<QuizResult>(`/device/courses/${code}/quiz`, {
        method: 'POST',
        body: JSON.stringify({
          quiz_id: paper.quiz_id,
          answers: paper.questions.map((q) => answers[q.id]),
        }),
      })
      setResult(res)
      setPaper(null)
      if (res.passed && course) {
        const done = { ...course, completed: true }
        saveCourse(done)
        setCourse(done)
      }
      void refresh() // the home screen should show the new tier and call minutes
    } catch (e) {
      setMessage(
        e instanceof NetworkError
          ? t('calls.needsConnection')
          : t(`education.err.${errorCode(e)}`, { defaultValue: t('education.err.ERROR') }),
      )
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
  const when = (iso: string | null) => (iso ? new Date(iso).toLocaleTimeString(lang) : '')

  return (
    <div className="space-y-6">
      <BackLink />
      <h1 className="text-3xl font-bold">{L(course.title, lang)}</h1>
      {offlineCopy && (
        <p role="status" data-testid="offline-copy">
          {t('education.offlineCopy')}
        </p>
      )}
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
          {result.certificate && (
            <Link
              to={`/resident/certificate/${result.certificate}`}
              className="mt-3 block underline"
              data-testid="certificate-link"
            >
              {t('education.viewCertificate')}
            </Link>
          )}
          {!result.passed && (
            <>
              {result.attempts?.retry_at && (
                <p data-testid="retry-at">
                  {t('education.tryAgainAt', { time: when(result.attempts.retry_at) })}
                </p>
              )}
              <button
                className={btn}
                onClick={() => {
                  setResult(null)
                  setStep(0)
                }}
              >
                {t('education.retry')}
              </button>
            </>
          )}
        </Card>
      ) : !onQuiz ? (
        <Card data-testid="lesson">
          <p className="text-sm">
            {t('education.lesson', { n: step + 1, total: course.lessons.length })}
          </p>
          <h2 className="text-2xl font-semibold">{L(course.lessons[step].title, lang)}</h2>
          <div className="mt-3">
            <Markdown source={L(course.lessons[step].body, lang)} />
          </div>
          <div className="flex gap-3">
            {step > 0 && (
              <button onClick={() => setStep(step - 1)} className={btn + ' bg-slate-700'}>
                {t('education.back')}
              </button>
            )}
            <button onClick={() => void next()} className={btn}>
              {step === course.lessons.length - 1 ? t('education.startQuiz') : t('education.next')}
            </button>
          </div>
        </Card>
      ) : !paper ? (
        <Card data-testid="quiz-intro">
          <h2 className="text-2xl font-semibold">{t('education.quiz')}</h2>
          <p>
            {t('education.quizInfo', {
              count: course.quiz.count,
              mark: Math.round(course.quiz.pass_mark * 100),
            })}
          </p>
          {pacing && (
            <p role="alert" data-testid="pacing">
              {pacing.code === 'COOLDOWN'
                ? t('education.cooldown', { time: when(pacing.retry_at) })
                : t('education.exhausted', { time: when(pacing.retry_at) })}
            </p>
          )}
          {message && <p role="alert">{message}</p>}
          <button onClick={() => void startQuiz()} className={btn} data-testid="begin-quiz">
            {t('education.beginQuiz')}
          </button>
          <button onClick={() => setStep(0)} className={btn + ' ml-3 bg-slate-700'}>
            {t('education.rereadLessons')}
          </button>
        </Card>
      ) : (
        <Card data-testid="quiz">
          <h2 className="text-2xl font-semibold">{t('education.quiz')}</h2>
          {paper.questions.map((q, qi) => (
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
            onClick={() => void handIn()}
            disabled={paper.questions.some((q) => answers[q.id] === undefined)}
            className={btn + ' disabled:opacity-40'}
          >
            {t('education.submit')}
          </button>
          {message && <p role="alert">{message}</p>}
        </Card>
      )}
    </div>
  )
}

export function CertificateCard({
  cert,
  lang,
  t,
}: {
  cert: CertificateData
  lang: string
  t: (k: string) => string
}) {
  return (
    <div className="rounded-lg border-4 border-double border-white p-6 text-center">
      <p className="text-sm uppercase">{t('education.certificateOf')}</p>
      <h2 className="mt-2 text-3xl font-bold">{L(cert.title, lang)}</h2>
      <p className="mt-2 text-xl">{cert.resident}</p>
      <p className="mt-2">
        {t('education.score')} {cert.score}
      </p>
      <p>{new Date(cert.issued_at).toLocaleDateString(lang)}</p>
      <p className="mt-2 font-mono text-sm">{cert.serial}</p>
    </div>
  )
}

export function Certificates() {
  const { t, i18n } = useTranslation()
  const { request } = useResident()
  const [certs, setCerts] = useState<CertificateData[] | null>(null)
  const [error, setError] = useState(false)
  useEffect(() => {
    request<CertificateData[]>('/device/certificates')
      .then(setCerts)
      .catch(() => setError(true))
  }, [request])
  return (
    <div className="space-y-6">
      <BackLink />
      <h1 className="text-3xl font-bold">{t('education.myCertificates')}</h1>
      {error && <p>{t('calls.needsConnection')}</p>}
      {certs?.length === 0 && <p>{t('education.noCertificates')}</p>}
      <ul className="space-y-3">
        {(certs ?? []).map((c) => (
          <li key={c.serial}>
            <Link to={`/resident/certificate/${c.serial}`} data-testid={`cert-${c.course}`}>
              <Card>
                <h2 className="text-xl font-semibold">{L(c.title, i18n.language)}</h2>
                <p className="font-mono text-sm">{c.serial}</p>
              </Card>
            </Link>
          </li>
        ))}
      </ul>
    </div>
  )
}

export function CertificateView() {
  const { t, i18n } = useTranslation()
  const { serial = '' } = useParams()
  const { request } = useResident()
  const [cert, setCert] = useState<CertificateData | null>(null)
  const [error, setError] = useState(false)
  useEffect(() => {
    request<CertificateData>(`/device/certificates/${serial}`)
      .then(setCert)
      .catch(() => setError(true))
  }, [request, serial])
  return (
    <div className="space-y-6">
      <BackLink />
      {error && <p>{t('calls.needsConnection')}</p>}
      {cert && <CertificateCard cert={cert} lang={i18n.language} t={t} />}
    </div>
  )
}
