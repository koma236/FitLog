import type { ImageAsset } from '../upload/types'
export type Comment = { id: string; post_id: string; body: string; created_at: string; updated_at: string; author: { id: string; username: string; display_name: string; avatar: ImageAsset | null }; is_owner: boolean }
export type CommentPage = { viewer_id: string; post_id: string; comment_count: number; items: Comment[]; next_cursor: string | null }
export type CommentResult = { viewer_id: string; post_id: string; comment_count: number; comment: Comment }
export type LikeResult = { viewer_id: string; post_id: string; like_count: number; is_liked: boolean }
export type SocialProps = { onIdentity: (next: import('../auth/api').Account | null, notice?: string) => void; onBusy: (token: symbol, busy: boolean) => void; onUncertain: (token: symbol, uncertain: boolean) => void }
