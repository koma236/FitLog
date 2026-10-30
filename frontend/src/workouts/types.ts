import type { ImageAsset } from '../upload/types'
export type Exercise = { name: string; sets: { weight_kg: string; reps: number }[] }
export type Visibility = { minutes: 'public' | 'private'; kind: 'public' | 'private' }
export type EnergyInput = { minutes?: number | null; kind?: string | null }
export type Workout = {
  image: ImageAsset | null; viewer_id: string; id: string; author: { id: string; username: string; display_name: string; avatar: ImageAsset | null }; is_owner: boolean
  performed_on: string; note: string; created_at: string; updated_at: string; exercises: Exercise[]
  energy: { kcal: number; method: 'met-gross-v1' } | null; energy_input: EnergyInput; visibility?: Visibility
}
export type Page = { viewer_id: string; items: Workout[]; next_cursor: string | null }
export const kinds: Record<string, string> = { general: '一般的な筋トレ', squat: 'スクワット・デッドリフト中心', vigorous: '高強度の筋トレ' }
