import { useState } from 'react'
import type { ImageAsset } from './types'
export default function Photo({ image, alt, avatar = false, onError }: { image: ImageAsset | null; alt: string; avatar?: boolean; onError?: () => void }) {
  const [failedUrl, setFailedUrl] = useState('')
  return image && failedUrl !== image.url ? <img className={avatar ? 'avatar-image' : 'workout-image'} src={image.url} width={image.width} height={image.height} alt={alt} referrerPolicy="no-referrer" loading="lazy" onError={() => { setFailedUrl(image.url); onError?.() }} /> : <span role={avatar ? 'img' : undefined} aria-label={avatar ? alt : undefined} className={avatar ? 'avatar-fallback' : 'image-fallback'}>{avatar ? <span aria-hidden="true">{alt.slice(0, 1)}</span> : image ? '画像を表示できません。再読み込みしてください。' : ''}</span>
}
