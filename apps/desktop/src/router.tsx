import { createBrowserRouter } from 'react-router-dom'
import { AppShell } from '@/components/app-shell'
import { LibraryScreen } from '@/routes/library-screen'
import { BookScreen } from '@/routes/book-screen'
import { SettingsScreen } from '@/routes/settings-screen'
import { NotesScreen } from '@/routes/notes-screen'

/** Top-level app routes (Phase 1): Library, a Book shell, Settings, and (T3+T4) Notes. */
export const router = createBrowserRouter([
  {
    element: <AppShell />,
    children: [
      { path: '/', element: <LibraryScreen /> },
      { path: '/book/:bookId', element: <BookScreen /> },
      { path: '/settings', element: <SettingsScreen /> },
      { path: '/notes', element: <NotesScreen /> },
    ],
  },
])
