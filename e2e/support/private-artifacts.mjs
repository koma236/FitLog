import { writeFileSync, renameSync } from 'node:fs'
import path from 'node:path'

/** Logical names are extension-free; all readers consume <name>.json. */
export function saveArtifact(directory, name, data) {
  if (!/^[a-z0-9-]+$/.test(name)) throw Error('ARTIFACT_NAME_INVALID')
  const target = path.join(directory, name + '.json'); const temporary = target + '.tmp'
  writeFileSync(temporary, JSON.stringify(data, null, 2), { mode: 0o600, flag: 'wx' })
  renameSync(temporary, target)
}
