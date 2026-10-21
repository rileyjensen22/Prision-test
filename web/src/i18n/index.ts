import i18n from 'i18next'
import { initReactI18next } from 'react-i18next'

import en from './en'
import es from './es'

i18n.use(initReactI18next).init({
  resources: { en: { translation: en }, es: { translation: es } },
  lng: 'en',
  fallbackLng: 'en',
  interpolation: { escapeValue: false },
})

export default i18n

/**
 * A separate translation instance, so a simulated resident screen can show a different language
 * without changing the app's own. Deliberately NOT given the react-i18next plugin (that would
 * replace the global instance); pass it to <I18nextProvider> instead.
 */
export function createI18n(lng: 'en' | 'es') {
  const instance = i18n.createInstance()
  void instance.init({
    resources: { en: { translation: en }, es: { translation: es } },
    lng,
    fallbackLng: 'en',
    interpolation: { escapeValue: false },
  })
  return instance
}
