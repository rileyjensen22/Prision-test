import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react'
import type { FormEvent, ReactNode } from 'react'

import { ShieldCheck } from 'lucide-react'
import { useTranslation } from 'react-i18next'

import { api, errorText, getToken, post, setToken } from './api'
import { Btn, FIELD, Notice } from './ui'

export type Role = 'officer' | 'supervisor' | 'admin' | 'auditor'
interface User {
  id: number
  username: string
  role: Role
}
interface AuthCtx {
  user: User | null
  loading: boolean
  login: (username: string, password: string) => Promise<void>
  logout: () => void
}

const Ctx = createContext<AuthCtx | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null)
  const [loading, setLoading] = useState(!!getToken())

  const loadMe = useCallback(async () => {
    try {
      setUser(await api<User>('/auth/me'))
    } catch {
      setUser(null)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    if (getToken()) void loadMe()
    const onLogout = () => setUser(null)
    window.addEventListener('isd-staff-logout', onLogout)
    return () => window.removeEventListener('isd-staff-logout', onLogout)
  }, [loadMe])

  const login = useCallback(
    async (username: string, password: string) => {
      const r = await post<{ token: string }>('/auth/login', { username, password })
      setToken(r.token)
      await loadMe()
    },
    [loadMe],
  )
  const logout = useCallback(() => {
    setToken(null)
    setUser(null)
  }, [])

  const value = useMemo(() => ({ user, loading, login, logout }), [user, loading, login, logout])
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>
}

export function useAuth(): AuthCtx {
  const c = useContext(Ctx)
  if (!c) throw new Error('useAuth outside provider')
  return c
}

export function LoginPage() {
  const { login } = useAuth()
  const { t } = useTranslation()
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)

  async function submit(e: FormEvent) {
    e.preventDefault()
    setError(null)
    try {
      await login(username, password)
    } catch (err) {
      setError(errorText(err))
    }
  }

  return (
    <div className="theme-staff grid min-h-screen place-items-center bg-bg p-6 text-body text-ink">
      <main className="w-full max-w-sm space-y-5 rounded-card border border-line bg-surface p-8">
        <div className="flex items-center gap-2 text-primary">
          <ShieldCheck aria-hidden="true" className="size-7" />
          <span className="text-h3 font-bold">{t('staff.brand')}</span>
        </div>
        <h1 className="text-h1 font-bold">{t('staff.signInTitle')}</h1>
        <form onSubmit={submit} className="space-y-4">
          <label className="block font-bold">
            {t('staff.username')}
            <input
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              autoComplete="username"
              className={`${FIELD} mt-1 font-normal`}
            />
          </label>
          <label className="block font-bold">
            {t('staff.password')}
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              autoComplete="current-password"
              className={`${FIELD} mt-1 font-normal`}
            />
          </label>
          {error && <Notice kind="err">{error}</Notice>}
          <Btn type="submit" className="w-full">
            {t('staff.signIn')}
          </Btn>
        </form>
      </main>
    </div>
  )
}
