import { create } from 'zustand'

/**
 * Visibility of the Reading Comfort Wizard (docs/10 §7). AppShell auto-opens it on first
 * run (`onboarding_complete !== true`); the Settings screen can re-open it anytime after.
 */
interface OnboardingWizardState {
  isOpen: boolean
  open: () => void
  close: () => void
}

export const useOnboardingWizardStore = create<OnboardingWizardState>((set) => ({
  isOpen: false,
  open: () => set({ isOpen: true }),
  close: () => set({ isOpen: false }),
}))
