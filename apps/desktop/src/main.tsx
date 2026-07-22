import '@fontsource-variable/inter'
import '@fontsource-variable/lexend'
import '@fontsource-variable/atkinson-hyperlegible-next'
import '@fontsource/opendyslexic'

import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.tsx'
import { initTheme } from './stores/theme'

initTheme()

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
