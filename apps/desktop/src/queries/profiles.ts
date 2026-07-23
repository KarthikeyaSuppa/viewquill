import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { api, type LoginResponse, type Profile } from '@/lib/api'
import { useAuthStore } from '@/stores/auth'

export interface CreateProfileInput {
  username: string
  password: string
  display_name?: string
  avatar: string
}

export interface LoginInput {
  username: string
  password: string
}

/** Lists local profiles (public — never includes a password/hash). */
export function useProfiles() {
  return useQuery({
    queryKey: ['profiles'],
    queryFn: () => api.get<Profile[]>('/profiles'),
  })
}

/** Creates a local profile (max 2; duplicate usernames rejected server-side). */
export function useCreateProfile() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (input: CreateProfileInput) => api.post<Profile>('/profiles', input),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['profiles'] })
    },
    onError: () => toast.error('Could not create the profile'),
  })
}

/** Logs a profile in; on success, starts the (memory-only) session and reloads settings. */
export function useLogin() {
  const queryClient = useQueryClient()
  const setSession = useAuthStore((s) => s.setSession)
  return useMutation({
    mutationFn: (input: LoginInput) => api.post<LoginResponse>('/auth/login', input),
    onSuccess: (data) => {
      setSession(data.token, data.user)
      // Settings (theme, reading comfort, delight) are per-profile server-side —
      // refetch so the switched-to profile's preferences apply immediately.
      queryClient.invalidateQueries({ queryKey: ['settings'] })
    },
    onError: () => toast.error('Incorrect username or password'),
  })
}

/** Logs the current profile out and returns the app to the profile picker. */
export function useLogout() {
  const queryClient = useQueryClient()
  const clear = useAuthStore((s) => s.clear)
  return useMutation({
    mutationFn: () => api.post<void>('/auth/logout'),
    onSettled: () => {
      // Always clear locally even if the network call fails — never trap the user
      // behind a stale session because the sidecar hiccuped.
      clear()
      queryClient.invalidateQueries({ queryKey: ['settings'] })
    },
    onError: () => toast.error('Could not reach the sidecar to log out — signing out locally'),
  })
}
