import { useEffect, useState } from 'react'
import { fileError } from './types'
export default function PhotoPicker({ file, onFile }: { file: File | null; onFile: (file: File | null) => void }) {
  const [preview, setPreview] = useState('')
  const [message, setMessage] = useState('')
  useEffect(() => { if (!file) { setPreview(''); return }; const url = URL.createObjectURL(file); setPreview(url); return () => { URL.revokeObjectURL(url) } }, [file])
  return <section><label className="field">写真（任意）<input type="file" accept="image/png,image/jpeg" onChange={event => { const next = event.target.files?.[0]; event.target.value = ''; if (!next) return; const error = fileError(next, false); setMessage(error); if (!error) onFile(next) }} /></label><p>PNG・JPEG、5MiB以下。写真は記録の保存後に追加します。</p>{message && <p role="alert">{message}</p>}{preview && <><img className="image-preview" src={preview} alt="選択した写真のプレビュー" referrerPolicy="no-referrer" /><button type="button" onClick={() => { onFile(null) }}>写真の選択を取り消す</button></>}</section>
}
