import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import { errorText, post } from '../api'
import { Badge, Btn, DataTable, ErrorLine, FIELD, Notice, Page, Panel, useLoad } from '../ui'
import type { Column } from '../ui'

interface Account {
  id: number
  username: string
  role: string
  active: boolean
  mfa_enabled: boolean
  must_change_password: boolean
}

type Step = { id: number; kind: 'password' | 'mfa' | 'active' }

/** Staff account administration (admins only). */
export default function Accounts() {
  const { t } = useTranslation()
  const { data, error, reload } = useLoad<Account[]>('/staff/accounts')
  const [step, setStep] = useState<Step | null>(null)
  const [reason, setReason] = useState('')
  const [msg, setMsg] = useState<{ kind: 'ok' | 'err'; text: string } | null>(null)
  const [name, setName] = useState('')
  const [role, setRole] = useState('officer')
  const [why, setWhy] = useState('')

  async function run(fn: () => Promise<string>) {
    setMsg(null)
    try {
      setMsg({ kind: 'ok', text: await fn() })
      setStep(null)
      setReason('')
      await reload()
    } catch (e) {
      setMsg({ kind: 'err', text: errorText(e) })
    }
  }

  function confirm(a: Account) {
    if (!step) return null
    const go = () =>
      void run(async () => {
        if (step.kind === 'password') {
          const r = await post<{ temporary_password: string }>(
            `/staff/accounts/${a.id}/reset-password`,
            { reason },
          )
          return t('staff.accounts.temp', { name: a.username, password: r.temporary_password })
        }
        if (step.kind === 'mfa') {
          await post(`/staff/accounts/${a.id}/reset-mfa`, { reason })
          return t('staff.accounts.okReset')
        }
        await post(`/staff/accounts/${a.id}/active`, { active: !a.active, reason })
        return t('staff.accounts.okActive')
      })
    return (
      <span className="flex flex-wrap gap-2">
        <input
          aria-label={t('staff.accounts.reason')}
          value={reason}
          onChange={(e) => setReason(e.target.value)}
        />
        <Btn disabled={reason.trim().length < 3} onClick={go}>
          {t('staff.accounts.confirm')}
        </Btn>
        <Btn kind="plain" onClick={() => setStep(null)}>
          {t('staff.accounts.cancel')}
        </Btn>
      </span>
    )
  }

  const columns: Column<Account>[] = [
    {
      key: 'user',
      header: t('staff.accounts.username'),
      sort: (a) => a.username,
      text: (a) => a.username,
      cell: (a) => <strong>{a.username}</strong>,
    },
    {
      key: 'role',
      header: t('staff.accounts.role'),
      sort: (a) => a.role,
      text: (a) => a.role,
      cell: (a) => a.role,
    },
    {
      key: 'state',
      header: t('staff.accounts.state'),
      cell: (a) => (
        <span className="flex flex-wrap gap-1">
          <Badge tone={a.active ? 'green' : 'red'}>
            {t('staff.accounts.active')}:{' '}
            {a.active ? t('staff.accounts.yes') : t('staff.accounts.no')}
          </Badge>
          <Badge tone={a.mfa_enabled ? 'green' : 'amber'}>
            {t('staff.accounts.mfa')}:{' '}
            {a.mfa_enabled ? t('staff.accounts.yes') : t('staff.accounts.no')}
          </Badge>
          {a.must_change_password && <Badge tone="amber">{t('staff.accounts.mustChange')}</Badge>}
        </span>
      ),
    },
    {
      key: 'action',
      header: t('staff.accounts.action'),
      cell: (a) =>
        step?.id === a.id ? (
          confirm(a)
        ) : (
          <span className="flex flex-wrap gap-2">
            <Btn kind="plain" onClick={() => setStep({ id: a.id, kind: 'password' })}>
              {t('staff.accounts.resetPassword')}
            </Btn>
            <Btn kind="plain" onClick={() => setStep({ id: a.id, kind: 'mfa' })}>
              {t('staff.accounts.resetMfa')}
            </Btn>
            <Btn kind="plain" onClick={() => setStep({ id: a.id, kind: 'active' })}>
              {a.active ? t('staff.accounts.deactivate') : t('staff.accounts.activate')}
            </Btn>
          </span>
        ),
    },
  ]

  return (
    <Page title={t('staff.accounts.title')}>
      <p className="text-ink-soft">{t('staff.accounts.intro')}</p>
      <ErrorLine error={error} />
      {msg && <Notice kind={msg.kind}>{msg.text}</Notice>}
      <DataTable
        columns={columns}
        rows={data ?? []}
        rowKey={(a) => a.id}
        testId="accounts"
        rowTestId={(a) => `account-${a.username}`}
      />
      <Panel title={t('staff.accounts.addTitle')} data-testid="account-form">
        <form
          className="flex flex-wrap items-end gap-3"
          onSubmit={(e) => {
            e.preventDefault()
            void run(async () => {
              const r = await post<{ username: string; temporary_password: string }>(
                '/staff/accounts',
                { username: name, role, reason: why },
              )
              setName('')
              setWhy('')
              return t('staff.accounts.temp', { name: r.username, password: r.temporary_password })
            })
          }}
        >
          <label className="block">
            {t('staff.accounts.username')}
            <input
              value={name}
              onChange={(e) => setName(e.target.value)}
              className={`${FIELD} mt-1`}
            />
          </label>
          <label className="block">
            {t('staff.accounts.role')}
            <select value={role} onChange={(e) => setRole(e.target.value)} className="mt-1 block">
              {['officer', 'supervisor', 'admin', 'auditor'].map((r) => (
                <option key={r} value={r}>
                  {r}
                </option>
              ))}
            </select>
          </label>
          <label className="block min-w-64 flex-1">
            {t('staff.accounts.reason')}
            <input
              value={why}
              onChange={(e) => setWhy(e.target.value)}
              className={`${FIELD} mt-1`}
            />
          </label>
          <Btn type="submit" disabled={name.trim().length < 3 || why.trim().length < 3}>
            {t('staff.accounts.create')}
          </Btn>
        </form>
      </Panel>
    </Page>
  )
}
