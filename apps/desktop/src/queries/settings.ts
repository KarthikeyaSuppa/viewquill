import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { api, type SettingsResponse } from '@/lib/api'

/** Reads live `app_settings` (docs/03) — theme/reading/delight keys applied app-wide. */
export function useSettings() {
  return useQuery({
    queryKey: ['settings'],
    queryFn: async () => (await api.get<SettingsResponse>('/settings')).values,
  })
}

/** Patches `app_settings`; callers pass only the keys that changed. */
export function useUpdateSettings() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (values: Record<string, unknown>) =>
      api.patch<SettingsResponse>('/settings', { values }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['settings'] })
    },
    onError: () => toast.error('Could not save settings'),
  })
}
