// Screenshots every resident and staff screen for the UI overhaul audit.
// Usage: node ui-audit/shoot.mjs <outDir>   (needs the e2e API on :8001 and the build on :4173)
// Synthetic e2e database only: language and text size are set straight in isd_e2e per run.
import { execFileSync } from 'node:child_process'
import { mkdirSync, readFileSync } from 'node:fs'
import { join } from 'node:path'

import { chromium } from '@playwright/test'

const out = process.argv[2]
if (!out) throw new Error('usage: shoot.mjs <outDir>')
const BASE = 'http://localhost:4173'
const fx = JSON.parse(readFileSync(join('e2e', '.fixtures.json'), 'utf8'))
const SIZES = { '1280x800': [1280, 800], '1024x600': [1024, 600], '1920x1080': [1920, 1080] }

function setResidents(language, textSize) {
  const sql = `update residents set language='${language}', text_size='${textSize}' where code like 'E2E-%'`
  execFileSync('su', ['postgres', '-c', `psql -q -d isd_e2e -c "${sql}"`])
}

// [name, resident, path, full matrix?]
const RESIDENT = [
  ['home-clear', 'fay', '/resident', true],
  ['home-locked', 'alice', '/resident', true],
  ['home-spanish-locked', 'benito', '/resident', false],
  ['locks', 'alice', '/resident/locks', true],
  ['why-locked', 'alice', '/resident/feature/calls', true],
  ['tier', 'carla', '/resident/tier', true],
  ['education', 'ned', '/resident/feature/basic_education', true],
  ['commissary', 'hal', '/resident/feature/commissary', true],
  ['calls', 'ivy', '/resident/feature/calls', true],
  ['calls-locked-tier', 'fay', '/resident/feature/texting', false],
  ['contacts', 'ivy', '/resident/feature/contact_requests', false],
  ['reading', 'fay', '/resident/feature/reading_general', false],
  ['rec', 'fay', '/resident/feature/out_of_cell_minimum', false],
  ['jobs', 'wren', '/resident/jobs', false],
  ['reentry', 'rex', '/resident/reentry', false],
  ['certificates', 'ned', '/resident/certificates', false],
  ['video-locked', 'fay', '/resident/feature/video', false],
  ['unpaired', null, '/resident', false],
]

const STAFF = [
  ['dashboard', '/staff'],
  ['roster', '/staff/roster'],
  ['devices', '/staff/devices'],
  ['intake', '/staff/intake'],
  ['outcomes', '/staff/outcomes'],
  ['confirmations', '/staff/confirmations'],
  ['appeals', '/staff/appeals'],
  ['outliers', '/staff/outliers'],
  ['view-as', '/staff/view-as'],
  ['mirror', '/staff/mirror'],
  ['out-of-cell', '/staff/out-of-cell'],
  ['schedule', '/staff/schedule'],
  ['welfare', '/staff/welfare'],
  ['contacts', '/staff/contacts'],
  ['monitoring', '/staff/monitoring'],
  ['content', '/staff/content'],
  ['finance', '/staff/finance'],
  ['config', '/staff/config'],
  ['audit', '/staff/audit'],
]

const browser = await chromium.launch({ executablePath: process.env.CHROMIUM_PATH || undefined })

async function residentShots() {
  const dir = join(out, 'resident')
  mkdirSync(dir, { recursive: true })
  for (const lang of ['en', 'es']) {
    for (const size of ['normal', 'large']) {
      setResidents(lang, size)
      for (const [sizeName, [width, height]] of Object.entries(SIZES)) {
        const ctx = await browser.newContext({ baseURL: BASE, viewport: { width, height } })
        for (const [name, who, path, full] of RESIDENT) {
          // Reduced matrix for secondary screens: one size, plus Spanish at large text.
          if (!full && !(sizeName === '1280x800' && (size === 'normal' || lang === 'es'))) continue
          const page = await ctx.newPage()
          await page.goto(who ? `${path}#device=${fx.tokens[who]}` : path)
          await page.waitForTimeout(700)
          await page.screenshot({
            path: join(dir, `${name}__${lang}__${size}__${sizeName}.png`),
            fullPage: true,
          })
          await page.close()
        }
        await ctx.close()
      }
    }
  }
  setResidents('en', 'normal')
}

async function staffShots() {
  const dir = join(out, 'staff')
  mkdirSync(dir, { recursive: true })
  for (const [sizeName, [width, height]] of Object.entries(SIZES)) {
    const ctx = await browser.newContext({ baseURL: BASE, viewport: { width, height } })
    const page = await ctx.newPage()
    await page.goto('/staff'.replace(/^/, BASE))
    await page.getByLabel('Username').fill('e2e_admin')
    await page.getByLabel('Password').fill(fx.staff_password)
    await page.screenshot({ path: join(dir, `login__${sizeName}.png`) })
    await page.getByRole('button', { name: 'Sign in' }).click()
    await page.getByTestId('whoami').waitFor()
    for (const [name, path] of STAFF) {
      // In-app navigation keeps the session (it lives in sessionStorage).
      await page.evaluate((p) => {
        window.history.pushState({}, '', p)
        window.dispatchEvent(new PopStateEvent('popstate'))
      }, path)
      await page.waitForTimeout(700)
      await page.screenshot({ path: join(dir, `${name}__${sizeName}.png`), fullPage: true })
    }
    await ctx.close()
  }
}

await residentShots()
await staffShots()
await browser.close()
console.log('done ->', out)
