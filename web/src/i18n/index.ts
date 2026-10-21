import i18n from 'i18next'
import { initReactI18next } from 'react-i18next'

const resources = {
  en: {
    translation: {
      residentHome: 'Resident Home',
      staffHome: 'Staff Dashboard',
      requestStaff: 'Request staff',
    },
  },
  es: {
    translation: {
      residentHome: 'Inicio del residente',
      staffHome: 'Panel del personal',
      requestStaff: 'Solicitar personal',
    },
  },
}

i18n
  .use(initReactI18next)
  .init({ resources, lng: 'en', fallbackLng: 'en', interpolation: { escapeValue: false } })

export default i18n
