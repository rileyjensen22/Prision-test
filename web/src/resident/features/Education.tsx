import { useCallback, useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link, useNavigate, useParams } from 'react-router-dom'
import {
  ArrowLeft,
  ArrowRight,
  Award,
  CheckCircle2,
  Layers,
  Lock,
  PlayCircle,
  RotateCcw,
  SendHorizontal,
} from 'lucide-react'

import { Button, LinkButton } from '../../ui/Button'
import { cn } from '../../ui/cn'
import { Notice } from '../../ui/Notice'
import { StatusBadge } from '../../ui/StatusBadge'
import { EmptyState, ErrorState, LoadingState } from '../../ui/States'
import { NetworkError } from '../api'
import { Card, ScreenFrame, reasonTitle } from '../components'
import { ProgressMeter } from '../parts'
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

export function Education() {
  const { t, i18n } = useTranslation()
  const { request, online } = useResident()
  const navigate = useNavigate()
  const [courses, setCourses] = useState<CourseSummary[] | null>(null)
  const [error, setError] = useState(false)

  const load = useCallback(() => {
    setError(false)
    request<CourseSummary[]>('/device/courses')
      .then(setCourses)
      .catch(() => setError(true))
  }, [request])
  useEffect(load, [load, online])

  return (
    <ScreenFrame title={t('education.title')}>
      <LinkButton
        to="/resident/certificates"
        icon={Award}
        className="self-start"
        data-testid="my-certificates"
      >
        {t('education.myCertificates')}
      </LinkButton>
      {error && <ErrorState title={t('calls.needsConnection')} onRetry={load} />}
      {!error && !courses && <LoadingState />}
      {courses?.length === 0 && (
        <EmptyState title={t('education.none', { defaultValue: t('education.title') })} />
      )}
      <ul className="grid gap-4 [grid-template-columns:repeat(auto-fill,minmax(24rem,1fr))]">
        {(courses ?? []).map((c) => {
          const pct = c.lessons ? Math.round((c.lessons_done / c.lessons) * 100) : 0
          return (
            <li key={c.code}>
              <Card
                data-testid={`course-${c.code}`}
                data-allowed={c.allowed}
                className={cn('flex h-full flex-col gap-3', !c.allowed && 'bg-lock-soft')}
              >
                <StatusBadge tone="neutral" icon={Layers} className="self-start">
                  {t(`education.${c.level}`)}
                </StatusBadge>
                <h2 className="text-h3 font-bold">{L(c.title, i18n.language)}</h2>
                {c.summary && <p className="text-ink-soft">{L(c.summary, i18n.language)}</p>}
                <div className="mt-auto space-y-3">
                  {c.allowed && (
                    <div className="rounded-full border-2 border-primary/40 bg-primary-soft">
                      <ProgressMeter
                        pct={pct}
                        label={t('education.progress', { done: c.lessons_done, total: c.lessons })}
                        tone="on-light"
                      />
                    </div>
                  )}
                  <p>{t('education.progress', { done: c.lessons_done, total: c.lessons })}</p>
                  {c.completed && (
                    <p
                      data-testid="course-done"
                      className="flex items-center gap-2 font-bold text-ok"
                    >
                      <CheckCircle2 aria-hidden="true" className="size-6" />
                      {t('education.done')}
                    </p>
                  )}
                  {c.certificate && (
                    <LinkButton
                      to={`/resident/certificate/${c.certificate}`}
                      variant="quiet"
                      icon={Award}
                    >
                      {t('education.viewCertificate')}
                    </LinkButton>
                  )}
                  {c.allowed ? (
                    <Button
                      variant={c.completed ? 'secondary' : 'primary'}
                      icon={PlayCircle}
                      onClick={() => navigate(`/resident/course/${c.code}`)}
                      className="w-full"
                    >
                      {c.completed
                        ? t('education.review')
                        : c.lessons_done
                          ? t('education.resume')
                          : t('education.start')}
                    </Button>
                  ) : (
                    <div data-testid="course-locked" className="space-y-1">
                      <p className="flex items-center gap-2 font-bold text-lock">
                        <Lock aria-hidden="true" className="size-6 shrink-0" />
                        {c.reasons[0] ? reasonTitle(t, c.reasons[0]) : t('education.lockedHint')}
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
                </div>
              </Card>
            </li>
          )
        })}
      </ul>
    </ScreenFrame>
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
      <ScreenFrame title={t('education.title')} narrow>
        {message ? <ErrorState title={message} /> : <LoadingState />}
      </ScreenFrame>
    )
  const onQuiz = step >= course.lessons.length
  const when = (iso: string | null) => (iso ? new Date(iso).toLocaleTimeString(lang) : '')

  return (
    <ScreenFrame title={L(course.title, lang)} narrow>
      {offlineCopy && (
        <Notice tone="info" role="status" data-testid="offline-copy">
          {t('education.offlineCopy')}
        </Notice>
      )}
      {result ? (
        <Card data-testid="quiz-result" className="space-y-3">
          <h2 className="text-h2 font-bold">
            {result.passed
              ? t('education.passed')
              : t('education.failed', { correct: result.correct, total: result.total })}
          </h2>
          {result.passed && (
            <p>{t('education.score', { correct: result.correct, total: result.total })}</p>
          )}
          {result.points_awarded > 0 && (
            <p data-testid="points-earned" className="text-label font-bold text-ok">
              {t('education.points', { n: result.points_awarded })}
            </p>
          )}
          {result.passed && result.already_completed && <p>{t('education.already')}</p>}
          {result.tier_after > result.tier_before && (
            <Notice tone="ok" data-testid="tier-up">
              <span className="font-bold">
                {t('education.tierUp', { from: result.tier_before, to: result.tier_after })}
              </span>
            </Notice>
          )}
          {result.calls_minutes_after != null &&
            result.calls_minutes_after !== result.calls_minutes_before && (
              <Notice tone="ok" data-testid="calls-up">
                <span className="font-bold">
                  {t('education.callsUp', {
                    from: result.calls_minutes_before,
                    to: result.calls_minutes_after,
                  })}
                </span>
              </Notice>
            )}
          {result.certificate && (
            <LinkButton
              to={`/resident/certificate/${result.certificate}`}
              icon={Award}
              data-testid="certificate-link"
              className="self-start"
            >
              {t('education.viewCertificate')}
            </LinkButton>
          )}
          {!result.passed && (
            <>
              {result.attempts?.retry_at && (
                <p data-testid="retry-at">
                  {t('education.tryAgainAt', { time: when(result.attempts.retry_at) })}
                </p>
              )}
              <Button
                variant="primary"
                icon={RotateCcw}
                onClick={() => {
                  setResult(null)
                  setStep(0)
                }}
              >
                {t('education.retry')}
              </Button>
            </>
          )}
        </Card>
      ) : !onQuiz ? (
        <Card data-testid="lesson" className="space-y-4">
          <p className="font-bold text-ink-soft">
            {t('education.lesson', { n: step + 1, total: course.lessons.length })}
          </p>
          <h2 className="text-h2 font-bold">{L(course.lessons[step].title, lang)}</h2>
          <div className="max-w-[60ch]">
            <Markdown source={L(course.lessons[step].body, lang)} />
          </div>
          <div className="flex flex-wrap gap-3 pt-2">
            {step > 0 && (
              <Button icon={ArrowLeft} onClick={() => setStep(step - 1)}>
                {t('education.back')}
              </Button>
            )}
            <Button variant="primary" icon={ArrowRight} onClick={() => void next()}>
              {step === course.lessons.length - 1 ? t('education.startQuiz') : t('education.next')}
            </Button>
          </div>
        </Card>
      ) : !paper ? (
        <Card data-testid="quiz-intro" className="space-y-4">
          <h2 className="text-h2 font-bold">{t('education.quiz')}</h2>
          <p>
            {t('education.quizInfo', {
              count: course.quiz.count,
              mark: Math.round(course.quiz.pass_mark * 100),
            })}
          </p>
          {pacing && (
            <Notice tone="notice" role="alert" data-testid="pacing">
              {pacing.code === 'COOLDOWN'
                ? t('education.cooldown', { time: when(pacing.retry_at) })
                : t('education.exhausted', { time: when(pacing.retry_at) })}
            </Notice>
          )}
          {message && (
            <Notice tone="danger" role="alert">
              {message}
            </Notice>
          )}
          <div className="flex flex-wrap gap-3">
            <Button
              variant="primary"
              icon={PlayCircle}
              onClick={() => void startQuiz()}
              data-testid="begin-quiz"
            >
              {t('education.beginQuiz')}
            </Button>
            <Button icon={ArrowLeft} onClick={() => setStep(0)}>
              {t('education.rereadLessons')}
            </Button>
          </div>
        </Card>
      ) : (
        <Card data-testid="quiz" className="space-y-6">
          <h2 className="text-h2 font-bold">{t('education.quiz')}</h2>
          {paper.questions.map((q, qi) => (
            <fieldset key={q.id} className="space-y-2" data-testid={`question-${qi}`}>
              <legend className="mb-2 text-label font-bold">
                {qi + 1}. {L(q.prompt, lang)}
              </legend>
              {q.choices.map((c, ci) => (
                <label
                  key={ci}
                  className={cn(
                    'flex min-h-touch cursor-pointer items-center gap-4 rounded-ctl border-2 px-4 py-2',
                    answers[q.id] === ci
                      ? 'border-primary bg-primary-soft font-bold'
                      : 'border-line bg-surface hover:border-primary',
                  )}
                >
                  <input
                    type="radio"
                    name={q.id}
                    checked={answers[q.id] === ci}
                    onChange={() => setAnswers({ ...answers, [q.id]: ci })}
                    className="size-6 accent-[var(--primary)]"
                  />
                  {L(c, lang)}
                </label>
              ))}
            </fieldset>
          ))}
          <Button
            variant="primary"
            icon={SendHorizontal}
            onClick={() => void handIn()}
            disabled={paper.questions.some((q) => answers[q.id] === undefined)}
          >
            {t('education.submit')}
          </Button>
          {message && (
            <Notice tone="danger" role="alert">
              {message}
            </Notice>
          )}
        </Card>
      )}
    </ScreenFrame>
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
    <div className="space-y-2 rounded-card border-4 border-double border-primary bg-surface p-8 text-center">
      <Award aria-hidden="true" className="mx-auto size-12 text-primary" strokeWidth={1.5} />
      <p className="text-sm font-bold text-ink-soft">{t('education.certificateOf')}</p>
      <h2 className="text-h1 font-bold">{L(cert.title, lang)}</h2>
      <p className="text-label">{cert.resident}</p>
      <p>
        {t('education.score')} {cert.score}
      </p>
      <p>{new Date(cert.issued_at).toLocaleDateString(lang)}</p>
      <p className="font-mono text-sm text-ink-soft">{cert.serial}</p>
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
    <ScreenFrame title={t('education.myCertificates')} narrow>
      {error && <ErrorState title={t('calls.needsConnection')} />}
      {certs?.length === 0 && <EmptyState title={t('education.noCertificates')} />}
      <ul className="space-y-3">
        {(certs ?? []).map((c) => (
          <li key={c.serial}>
            <Link
              to={`/resident/certificate/${c.serial}`}
              data-testid={`cert-${c.course}`}
              className="block"
            >
              <Card className="flex items-center gap-4 hover:border-primary">
                <Award
                  aria-hidden="true"
                  className="size-9 shrink-0 text-primary"
                  strokeWidth={1.75}
                />
                <div>
                  <h2 className="text-label font-bold">{L(c.title, i18n.language)}</h2>
                  <p className="font-mono text-sm text-ink-soft">{c.serial}</p>
                </div>
              </Card>
            </Link>
          </li>
        ))}
      </ul>
    </ScreenFrame>
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
    <ScreenFrame title={t('education.myCertificates')} narrow>
      {error && <ErrorState title={t('calls.needsConnection')} />}
      {cert && <CertificateCard cert={cert} lang={i18n.language} t={t} />}
    </ScreenFrame>
  )
}
