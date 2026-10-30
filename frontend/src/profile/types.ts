import type { ImageAsset } from '../upload/types'
export const healthKeys = ['height', 'weight', 'age', 'formula', 'activity'] as const
export const energyKeys = ['bmr', 'tdee', 'intake'] as const
export const profileKeys = [...healthKeys, ...energyKeys] as const
export type ProfileKey = typeof profileKeys[number]
export type Visibility = Record<ProfileKey, 'public' | 'private'>
export type Health = { height: string | null; weight: string | null; age: number | null; formula: string | null; activity: string | null }
export type Energy = { bmr: number | null; tdee: number | null; intake: number | null }
export type Profile = { viewer_id: string; avatar: ImageAsset | null; id: string; username: string; display_name: string; bio: string; is_owner: boolean; health: Partial<Health>; energy: Partial<Energy>; visibility?: Visibility }
export const labels: Record<ProfileKey, string> = { height: '身長', weight: '体重', age: '年齢', formula: '計算式の区分', activity: '普段の活動量', bmr: '基礎代謝の目安', tdee: '1日の推定消費量', intake: '体重維持の摂取目安' }
export const formulas: Record<string, string> = { male: '男性式', female: '女性式' }
export const activities: Record<string, string> = { low: '低い（日常は座っていることが多い）', medium: 'ふつう（日常的によく動く）', high: '高い（活発な仕事・運動習慣）' }
export const privateFlags = (): Visibility => ({ height: 'private', weight: 'private', age: 'private', formula: 'private', activity: 'private', bmr: 'private', tdee: 'private', intake: 'private' })
