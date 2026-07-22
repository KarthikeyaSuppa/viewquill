import { useQuery } from '@tanstack/react-query'
import { api, type HealthResponse } from '@/lib/api'

/** Polls the sidecar `/health` endpoint (docs/02) so the boot screen can reflect status live. */
export function useHealth() {
  return useQuery({
    queryKey: ['health'],
    queryFn: () => api.get<HealthResponse>('/health'),
    refetchInterval: 5000,
  })
}
