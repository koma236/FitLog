import local from './playwright.config.js'
import { aws, artifact, ORIGIN } from './support/environment.js'
if (!aws) throw Error('AWS_RUNTIME_REQUIRED')
export default { ...local, outputDir: artifact + '/playwright',
  use: { ...local.use, baseURL: ORIGIN, ignoreHTTPSErrors: false } }
