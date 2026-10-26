import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import { errorText, post } from '../api'
import { useAuth } from '../auth'
import { Btn, FIELD, Notice, Page, Panel } from '../ui'

/** Change password and set up two-step sign-in. Also the only page open when either is required. */
export default function Security() {
  const { t } = useTranslation()
  const { user, restricted, adopt } = useAuth()
  const [current, setCurrent] = useState('')
  const [next, setNext] = useState('')
  const [msg, setMsg] = useState<{ kind: 'ok' | 'err'; text: string } | null>(null)
  const [setup, setSetup] = useState<{ secret: string; otpauth_uri: string } | null>(null)
  const [code, setCode] = useState('')
  const [codes, setCodes] = useState<string[] | null>(null)

  async function changePassword() {
    setMsg(null)
    try {
      const r = await post<{ token: string }>('/auth/change-password', {
        current_password: current,
        new_password: next,
      })
      setCurrent('')
      setNext('')
      setMsg({ kind: 'ok', text: t('staff.security.changed') })
      await adopt(r.token)
    } catch (e) {
      setMsg({ kind: 'err', text: errorText(e) })
    }
  }

  async function startSetup() {
    setMsg(null)
    try {
      setSetup(await post<{ secret: string; otpauth_uri: string }>('/auth/mfa/setup'))
    } catch (e) {
      setMsg({ kind: 'err', text: errorText(e) })
    }
  }

  async function confirm() {
    setMsg(null)
    try {
      const r = await post<{ recovery_codes: string[]; token: string }>('/auth/mfa/enable', {
        code,
      })
      setCodes(r.recovery_codes)
      setSetup(null)
      setCode('')
      setMsg({ kind: 'ok', text: t('staff.security.mfaDone') })
      await adopt(r.token)
    } catch (e) {
      setMsg({ kind: 'err', text: errorText(e) })
    }
  }

  return (
    <Page title={t('staff.security.title')}>
      {user?.must_change_password && (
        <Notice kind="err">{t('staff.security.forcedPassword')}</Notice>
      )}
      {restricted && <Notice kind="err">{t('staff.security.forcedMfa')}</Notice>}
      {msg && <Notice kind={msg.kind}>{msg.text}</Notice>}

      <Panel title={t('staff.security.passwordTitle')} data-testid="password-panel">
        <p className="mb-3 text-ink-soft">{t('staff.security.rules')}</p>
        <div className="grid max-w-md gap-3">
          <label className="block">
            {t('staff.security.current')}
            <input
              type="password"
              value={current}
              onChange={(e) => setCurrent(e.target.value)}
              autoComplete="current-password"
              className={`${FIELD} mt-1`}
            />
          </label>
          <label className="block">
            {t('staff.security.newPassword')}
            <input
              type="password"
              value={next}
              onChange={(e) => setNext(e.target.value)}
              autoComplete="new-password"
              className={`${FIELD} mt-1`}
            />
          </label>
          <Btn disabled={!current || next.length < 12} onClick={() => void changePassword()}>
            {t('staff.security.change')}
          </Btn>
        </div>
      </Panel>

      <Panel title={t('staff.security.mfaTitle')} data-testid="mfa-panel">
        <p className="mb-3">
          {user?.mfa_enabled ? t('staff.security.mfaOn') : t('staff.security.mfaOff')}
        </p>
        {!user?.mfa_enabled && !setup && (
          <Btn onClick={() => void startSetup()}>{t('staff.security.mfaStart')}</Btn>
        )}
        {setup && (
          <div className="grid max-w-xl gap-3">
            <p>
              <strong>{t('staff.security.mfaSecret')}</strong>
              <br />
              <code data-testid="mfa-secret" className="break-all text-h3">
                {setup.secret}
              </code>
            </p>
            <p className="break-all text-ink-soft">
              {t('staff.security.mfaUri')}: {setup.otpauth_uri}
            </p>
            <label className="block">
              {t('staff.security.mfaCode')}
              <input
                value={code}
                onChange={(e) => setCode(e.target.value)}
                inputMode="numeric"
                autoComplete="one-time-code"
                className={`${FIELD} mt-1`}
              />
            </label>
            <Btn disabled={code.trim().length < 6} onClick={() => void confirm()}>
              {t('staff.security.mfaConfirm')}
            </Btn>
          </div>
        )}
        {codes && (
          <div className="mt-4" data-testid="recovery-codes">
            <h3 className="font-bold">{t('staff.security.recoveryTitle')}</h3>
            <p className="mb-2 text-ink-soft">{t('staff.security.recoveryNote')}</p>
            <ul className="grid max-w-md grid-cols-2 gap-2 font-mono">
              {codes.map((c) => (
                <li key={c} className="rounded-ctl bg-surface-2 px-2 py-1">
                  {c}
                </li>
              ))}
            </ul>
          </div>
        )}
      </Panel>
    </Page>
  )
}
