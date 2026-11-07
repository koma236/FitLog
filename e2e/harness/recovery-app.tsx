// Fixture entry only. Product components and fetch/DOM logic are unmodified.
import { createRoot } from 'react-dom/client'
import { StrictMode } from 'react'
import App from '../../frontend/src/App'
createRoot(document.getElementById('root')!).render(<StrictMode><App /></StrictMode>)
