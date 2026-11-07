import { test, expect, type Browser, type BrowserContext, type Page, type Request } from '@playwright/test'
import { writeFileSync, mkdirSync } from 'node:fs'
import { randomUUID } from 'node:crypto'
import path from 'node:path'
import { STEP_IDS, ResultLedger, ORIGIN, sanitizeFailure, captureSearchAllowed, withinDeadline, withinCancellableDeadline, modalFocusContained, type CancellationScope } from '../support/safety.mjs'
import { api, artifact, audit, authSlot, budget, fillRecord, go, guardedContext, guardedPage, imageFixture, keyboardTarget, login, logout, makeActor, responseFor, recoveryLog, runId, scan, signup, type Actor } from '../support/app.js'
import { deletionSettled, networkRecovery, recoveryCases, recoveryRows, sessionMatches } from '../support/recovery.mjs'

// Narrow characterization: Playwright's implicit-label text includes textarea's
// DOM text, while the textbox accessible name correctly excludes its own value.
test('edit locators keep the textbox name when an implicit label contains a value', async ({ browser }) => {
  const context = await guardedContext(browser)
  try {
    const page = await guardedPage(context)
    await page.setContent('<label>コメント本文<textarea>old body</textarea></label>')
    await expect(page.getByRole('textbox', { name: 'コメント本文', exact: true })).toHaveValue('old body')
    await page.getByRole('textbox', { name: 'コメント本文', exact: true }).fill('edited body')
    await expect(page.getByRole('textbox', { name: 'コメント本文', exact: true })).toHaveValue('edited body')
  } finally { await context.close() }
})

test('native modal focus permits browser chrome and rejects nonmodal background focus', async ({ browser }) => {
  const context = await guardedContext(browser)
  try {
    const page = await guardedPage(context)
    await page.setContent('<button id="outside">open</button><dialog><button id="cancel">cancel</button><button>delete</button></dialog>')
    await page.evaluate(() => { document.querySelector('dialog')!.showModal(); document.querySelector<HTMLButtonElement>('#cancel')!.focus() })
    for (const key of ['Tab', 'Tab', 'Tab', 'Shift+Tab', 'Shift+Tab', 'Shift+Tab']) {
      await page.keyboard.press(key)
      expect(await page.locator('dialog').evaluate(modalFocusContained)).toBe(true)
    }
    await page.evaluate(() => { const dialog = document.querySelector('dialog')!; dialog.close(); dialog.show(); document.querySelector<HTMLButtonElement>('#outside')!.focus() })
    expect(await page.locator('dialog').evaluate(modalFocusContained)).toBe(false)
  } finally { await context.close() }
})

test('capture verifies the masked DOM before exposing an exact synthetic result', async ({ browser }) => {
  const context = await guardedContext(browser)
  try {
    const page = await guardedPage(context)
    await page.setContent('<style id="fitlog-capture-privacy">.user-results{visibility:hidden!important}</style><ul class="user-results"><li><a href="#profile/synthetic_a">Synthetic A</a></li></ul>')
    await expect(page.getByRole('link', { name: 'Synthetic A', exact: true })).toHaveCount(0)
    const link = page.locator('.user-results > li > a')
    await expect(link).toHaveText('Synthetic A')
    await expect(link).toHaveAttribute('href', '#profile/synthetic_a')
    await expect(link).toBeHidden()
    await page.locator('#fitlog-capture-privacy').evaluate(element => element.remove())
    await expect(page.getByRole('link', { name: 'Synthetic A', exact: true })).toBeVisible()
  } finally { await context.close() }
})

test('two members use the real local application', async ({ browser }) => {
  // Each ledger case is bounded below; the full journey has a separate 15min cap.
  test.setTimeout(900_000)
  const ledger = new ResultLedger(STEP_IDS)
  const resources: { users: string[]; posts: { id: string; actor: Actor }[]; comments: string[] } = { users: [], posts: [], comments: [] }
  let checkpoint = 'initial'
  let failed = false
  let captureStatus = 'not_run'
  let unconfirmedWritesOnTimeout = false
  let a: Actor | undefined
  let b: Actor | undefined
  let aPost = ''
  let bPost = ''
  let comment = ''
  let recordPayload: Record<string, unknown> = {}
  const noteA = `A record ${runId}`
  const noteB = `B record ${runId}`
  const noteEdited = `Edited ${runId}`
  const cleanup: { action: string; status: string }[] = []
  const failures: { source: string; line: number | null; column: number | null }[] = []
  const recovery = recoveryRows()

  const save = () => writeFileSync(path.join(artifact, 'journey.json'), JSON.stringify({
    run_id: runId, checkpoint, failures, recovery, capture_status: captureStatus, unconfirmed_writes_on_timeout: unconfirmedWritesOnTimeout, steps: ledger.rows(), resources: {
      users: resources.users, posts: resources.posts.map(row => row.id), comments: resources.comments,
    }, cleanup, browsers: { chromium: browser.version(), firefox: 'not_run', webkit: 'not_run' },
    aws: 'not_run', natural_session_expiry: 'not_run', server_restart: 'not_run', native_file_picker_manual: 'not_run',
  }, null, 2))
  const mark = (value: string) => { checkpoint = value; save() }
  const step = async (id: string, action: () => Promise<void>) => {
    ledger.start(id); mark(id)
    try {
      await withinDeadline(action, 120_000, async () => {
        unconfirmedWritesOnTimeout = true
        // Closing both contexts prevents the timed-out case from issuing later UI writes.
        await Promise.allSettled([a?.context.close(), b?.context.close()])
      })
      ledger.finish(id, true)
    } catch (error) { failures.push(sanitizeFailure(error)); ledger.finish(id, false); throw new Error('CASE_FAILED') }
    finally { save() }
  }
  const openPost = async (actor: Actor, id: string) => {
    await go(actor.page, '#record/' + id)
    await expect(actor.page.locator('article.workout-card')).toBeVisible()
    await expect(actor.page.getByRole('textbox', { name: 'コメント本文', exact: true })).toBeVisible()
  }

  try {
    a = await makeActor(browser, 'a'); b = await makeActor(browser, 'b')
    const A = a; const B = b
    await step('E01', async () => {
      await A.page.goto(ORIGIN)
      for (const width of [1280, 375]) {
        await A.page.setViewportSize({ width, height: width === 375 ? 812 : 800 })
        await scan(A.page, `login-${width}`)
        await A.page.getByRole('button', { name: '新規登録', exact: true }).click()
        await scan(A.page, `signup-${width}`)
        await A.page.getByRole('button', { name: 'ログイン画面へ', exact: true }).click()
      }
      await A.page.setViewportSize({ width: 1280, height: 800 })
      mark('E01-register-A'); await signup(A); resources.users.push(A.id)
      mark('E01-register-B'); await signup(B); resources.users.push(B.id)
      mark('E01-empty-following')
      await expect(B.page.getByText('まだ記録がありません。', { exact: true })).toBeVisible()
      mark('E01-logout-A'); await logout(A)
      await A.page.getByRole('button', { name: '新規登録', exact: true }).click()
      await A.page.getByLabel('ユーザー名', { exact: true }).fill(A.username)
      await A.page.getByLabel('表示名', { exact: true }).fill(A.name)
      await A.page.getByLabel('メールアドレス', { exact: true }).fill(A.email)
      await A.page.getByLabel('パスワード', { exact: true }).fill(A.password)
      mark('E01-duplicate'); await authSlot()
      const duplicate = await responseFor(A.page, '/api/auth/signup', 'POST', () => A.page.getByRole('button', { name: '登録する', exact: true }).click(), 409)
      expect((await duplicate.json()).code).toBe('DUPLICATE_USERNAME')
      mark('E01-invalid-login'); await login(A, true)
      mark('E01-valid-login'); await login(A)
    })

    await step('E02', async () => {
      await go(A.page, '#profile-edit'); await scan(A.page, 'profile-edit-desktop')
      A.name = `更新A ${runId}`
      await A.page.getByLabel('表示名', { exact: true }).fill(A.name)
      await A.page.getByLabel('自己紹介', { exact: true }).fill(`合成プロフィール ${runId}`)
      await responseFor(A.page, '/api/users/me', 'PUT', () => A.page.getByRole('button', { name: '変更を保存', exact: true }).click(), 200)
      await go(A.page, '#profile')
      budget.take('images')
      await A.page.getByLabel('アバターを選択', { exact: true }).setInputFiles(imageFixture())
      await responseFor(A.page, '/api/users/me/avatar', 'PUT', () => A.page.getByRole('button', { name: '画像を保存', exact: true }).click(), 200)
      await A.page.reload()
      await expect(A.page.getByText(`合成プロフィール ${runId}`, { exact: true })).toBeVisible()
      await scan(A.page, 'profile-self-desktop')
      await go(B.page, '#profile/' + A.username)
      await expect(B.page.getByRole('heading', { name: A.name, exact: true })).toBeVisible()
      await expect(B.page.locator('img.avatar-image').first()).toBeVisible()
      const profile = (await api(B, '/api/users/' + A.username)).body
      expect(profile).not.toHaveProperty('email'); expect(profile).not.toHaveProperty('visibility')
      expect(profile.health).toEqual({})
      await scan(B.page, 'profile-other-desktop')
    })

    await step('E03', async () => {
      await A.page.setViewportSize({ width: 375, height: 812 })
      await go(A.page, '#record-new'); await scan(A.page, 'record-new-mobile')
      await fillRecord(A.page, noteA)
      budget.take('images'); budget.take('posts')
      const [chooser] = await Promise.all([
        A.page.waitForEvent('filechooser'),
        A.page.getByLabel('写真（任意）', { exact: true }).press('Space'),
      ])
      await chooser.setFiles(imageFixture())
      const response = await responseFor(A.page, '/api/posts', 'POST', () => A.page.getByRole('button', { name: '記録する', exact: true }).click(), 201)
      aPost = (await response.json()).id; resources.posts.push({ id: aPost, actor: A }); save()
      await expect(A.page.getByText('画像を保存しました。', { exact: true })).toBeVisible()
      // Photo creation intentionally stays on #record-new; open its permanent UI link.
      await A.page.getByRole('link', { name: '記録を開き直す', exact: true }).click()
      await A.page.reload()
      const value = (await api(A, '/api/posts/' + aPost)).body
      expect(value.performed_on).toBe('2026-01-15'); expect(value.note).toBe(noteA)
      expect(value.exercises[0].name).toBe('ベンチプレス')
      expect(value.exercises[0].sets).toHaveLength(3)
      for (const row of value.exercises[0].sets) { expect(Number(row.weight_kg)).toBe(60); expect(row.reps).toBe(10) }
      recordPayload = { performed_on: value.performed_on, exercises: value.exercises, note: noteEdited, energy_input: value.energy_input, visibility: value.visibility }
      await expect(A.page.getByText(noteA, { exact: true })).toBeVisible()
      await expect.poll(() => A.page.locator('img.workout-image').first().evaluate((element: HTMLImageElement) => element.naturalWidth)).toBeGreaterThan(0)
      await scan(A.page, 'record-detail-mobile')
      await go(B.page, '#record-new'); await fillRecord(B.page, noteB, 1); budget.take('posts')
      const responseB = await responseFor(B.page, '/api/posts', 'POST', () => B.page.getByRole('button', { name: '記録する', exact: true }).click(), 201)
      bPost = (await responseB.json()).id; resources.posts.push({ id: bPost, actor: B })
      await openPost(B, aPost); await expect(B.page.getByText(noteA, { exact: true })).toBeVisible()
    })

    await step('E04', async () => {
      await B.page.setViewportSize({ width: 375, height: 812 })
      const emptySearch = await responseFor(B.page, '/api/users/search', 'GET', () => go(B.page, '#search'), 200)
      // OpenAPI specifies date_joined DESC/id DESC for empty search as well.
      const emptyItems = (await emptySearch.json()).items.map((item: { id: string }) => item.id)
      expect(emptyItems).toContain(A.id); expect(emptyItems).toContain(B.id)
      await expect(B.page.getByRole('link', { name: A.name, exact: true })).toBeVisible()
      await expect(B.page.getByRole('link', { name: B.name, exact: true })).toBeVisible()
      await scan(B.page, 'search-empty-mobile')
      for (const q of ['%', '_', runId + '%', runId + '__', `fl10a_${runId}_missing`]) {
        await B.page.getByLabel('ユーザー名・表示名', { exact: true }).fill(q)
        const response = await responseFor(B.page, '/api/users/search', 'GET', () => B.page.getByRole('button', { name: '検索', exact: true }).click(), 200)
        const values = (await response.json()).items
        // '%' is literal. '_' legitimately matches our usernames, so test each returned string.
        expect(values.every((item: { username: string; display_name: string }) => item.username.includes(q) || item.display_name.includes(q))).toBe(true)
        if (q.startsWith(runId)) expect(values).toHaveLength(0)
        if (q.includes('missing')) await expect(B.page.getByText('ユーザーが見つかりません。', { exact: true })).toBeVisible()
      }
      await B.page.getByLabel('ユーザー名・表示名', { exact: true }).fill(A.username.slice(3))
      await responseFor(B.page, '/api/users/search', 'GET', () => B.page.getByRole('button', { name: '検索', exact: true }).click(), 200)
      await expect(B.page.getByRole('link', { name: A.name, exact: true })).toBeVisible()
      await scan(B.page, 'search-results-mobile')
      await B.page.getByRole('link', { name: A.name, exact: true }).click()
      await responseFor(B.page, '/api/users/' + A.id + '/follow', 'POST', () => B.page.getByRole('button', { name: 'フォローする', exact: true }).click(), 200)
      await go(B.page, '#')
      await expect(B.page.getByText(noteA, { exact: true })).toBeVisible(); await expect(B.page.getByText(noteB, { exact: true })).toBeVisible()
      await scan(B.page, 'following-mobile')
      await B.page.getByRole('tab', { name: 'すべて', exact: true }).click()
      await expect(B.page.getByText(noteA, { exact: true })).toBeVisible(); await scan(B.page, 'all-mobile')
      await go(B.page, '#profile/' + A.username)
      await responseFor(B.page, '/api/users/' + A.id + '/follow', 'DELETE', () => B.page.getByRole('button', { name: 'フォローを解除', exact: true }).click(), 200)
      await go(B.page, '#'); await expect(B.page.getByText(noteB, { exact: true })).toBeVisible()
      await expect(B.page.getByText(noteA, { exact: true })).toHaveCount(0)
    })

    await step('E05', async () => {
      await openPost(B, aPost)
      await responseFor(B.page, '/api/posts/' + aPost + '/like', 'POST', () => B.page.getByRole('button', { name: 'いいね', exact: true }).click(), 200)
      await B.page.reload(); await expect(B.page.getByRole('button', { name: 'いいね', exact: true })).toHaveAttribute('aria-pressed', 'true')
      expect((await api(A, '/api/posts/' + aPost)).body.like_count).toBe(1)
      await responseFor(B.page, '/api/posts/' + aPost + '/like', 'DELETE', () => B.page.getByRole('button', { name: 'いいね', exact: true }).click(), 200)
      expect((await api(A, '/api/posts/' + aPost)).body.like_count).toBe(0)
      budget.take('comments')
      await B.page.getByRole('textbox', { name: 'コメント本文', exact: true }).fill(`comment ${runId}`)
      const response = await responseFor(B.page, '/api/posts/' + aPost + '/comments', 'POST', () => B.page.getByRole('button', { name: 'コメントする', exact: true }).click(), 201)
      comment = (await response.json()).comment.id; resources.comments.push(comment)
      await B.page.reload()
      const row = B.page.locator('article.comment-row').filter({ hasText: `comment ${runId}` })
      await row.getByRole('button', { name: '編集', exact: true }).click()
      await B.page.getByRole('textbox', { name: 'コメント本文', exact: true }).fill(`updated comment ${runId}`)
      await responseFor(B.page, '/api/comments/' + comment, 'PUT', () => B.page.getByRole('button', { name: '変更を保存', exact: true }).click(), 200)
      expect((await api(A, '/api/posts/' + aPost)).body.comment_count).toBe(1)
      await A.page.reload(); await expect(A.page.getByText(`updated comment ${runId}`, { exact: true })).toBeVisible()
      // E06 comment authorization must run while B's comment still exists.
      for (const method of ['PUT', 'DELETE']) {
        const result = await api(A, '/api/comments/' + comment, method, method === 'PUT' ? { body: 'forbidden change' } : undefined)
        expect(result.status).toBe(403); expect(result.body.code).toBe('FORBIDDEN')
      }
      expect((await api(B, '/api/comments/' + comment)).body.comment.body).toBe(`updated comment ${runId}`)
      await B.page.reload()
      await B.page.locator('article.comment-row').getByRole('button', { name: '削除', exact: true }).click()
      await responseFor(B.page, '/api/comments/' + comment, 'DELETE', () => B.page.getByRole('button', { name: 'コメントを削除する', exact: true }).click(), 204)
      resources.comments = []
      await A.page.reload(); expect((await api(A, '/api/posts/' + aPost)).body.comment_count).toBe(0)
    })

    await step('E06', async () => {
      await go(A.page, '#record-edit/' + aPost); await scan(A.page, 'record-edit-mobile')
      await A.page.getByLabel('メモ', { exact: true }).fill(noteEdited)
      await responseFor(A.page, '/api/posts/' + aPost, 'PUT', () => A.page.getByRole('button', { name: '変更を保存', exact: true }).click(), 200)
      budget.take('images')
      await A.page.getByLabel('記録画像を選択', { exact: true }).setInputFiles(imageFixture())
      await responseFor(A.page, '/api/posts/' + aPost + '/image', 'PUT', () => A.page.getByRole('button', { name: '画像を保存', exact: true }).click(), 200)
      await A.page.reload(); await expect(A.page.getByText(noteEdited, { exact: true })).toBeVisible()
      await openPost(B, aPost)
      await expect(B.page.getByRole('link', { name: '編集', exact: true })).toHaveCount(0)
      await go(B.page, '#record-edit/' + aPost)
      await expect(B.page.getByText('この記録は編集できません。', { exact: true })).toBeVisible()
      await expect(B.page.getByRole('form', { name: '記録フォーム', exact: true })).toHaveCount(0)
      for (const method of ['PUT', 'DELETE']) {
        const result = await api(B, '/api/posts/' + aPost, method, method === 'PUT' ? recordPayload : undefined)
        expect(result.status).toBe(403); expect(result.body.code).toBe('FORBIDDEN')
      }
      expect((await api(A, '/api/posts/' + aPost)).body.note).toBe(noteEdited)
    })

    await step('E07', async () => {
      await go(A.page, '#record-new'); await fillRecord(A.page, `invalid ${runId}`, 1)
      await A.page.getByLabel('種目1 セット1 回数', { exact: true }).fill('0')
      const beforeInvalid = (await api(A, '/api/users/' + A.username + '/posts')).body.items.map((item: { id: string }) => item.id)
      const response = await responseFor(A.page, '/api/posts', 'POST', () => A.page.getByRole('button', { name: '記録する', exact: true }).click(), 400)
      expect((await response.json()).code).toBe('VALIDATION_ERROR')
      const invalidId = response.request().postDataJSON().id as string
      const invalidRead = await api(A, '/api/posts/' + invalidId)
      if (invalidRead.status === 200) resources.posts.push({ id: invalidId, actor: A })
      expect(invalidRead.status).toBe(404)
      expect((await api(A, '/api/users/' + A.username + '/posts')).body.items.map((item: { id: string }) => item.id)).toEqual(beforeInvalid)
      await scan(A.page, 'validation-error-mobile')
      await openPost(B, aPost)
      let uiCommentWrites = 0
      const commentRequest = (request: Request) => {
        if (request.method() === 'POST' && new URL(request.url()).pathname === '/api/posts/' + aPost + '/comments') uiCommentWrites++
      }
      B.page.on('request', commentRequest)
      try {
        await B.page.getByRole('textbox', { name: 'コメント本文', exact: true }).fill('   ')
        await B.page.getByRole('button', { name: 'コメントする', exact: true }).click()
        await expect(B.page.getByRole('alert').filter({ hasText: /コメント.*1.*500/ })).toBeVisible()
        expect(uiCommentWrites).toBe(0)
      } finally { B.page.off('request', commentRequest) }
      const blankComment = await api(B, '/api/posts/' + aPost + '/comments', 'POST', { id: randomUUID(), body: '   ' })
      if (blankComment.status === 201) resources.comments.push(blankComment.body.comment.id)
      expect(blankComment.status).toBe(400); expect(blankComment.body.code).toBe('VALIDATION_ERROR')
      expect((await api(B, '/api/posts/' + aPost)).body.comment_count).toBe(0)
      await openPost(A, aPost)
      const prior = (await api(A, '/api/posts/' + aPost)).body.image.id
      await A.page.getByLabel('記録画像を選択', { exact: true }).setInputFiles({ name: 'oversize.png', mimeType: 'image/png', buffer: Buffer.alloc(5 * 1024 * 1024 + 1) })
      await expect(A.page.getByRole('alert').filter({ hasText: /5MiB/ })).toBeVisible()
      await A.page.getByLabel('記録画像を選択', { exact: true }).setInputFiles({ name: 'fake.png', mimeType: 'image/png', buffer: Buffer.from('This is not an image') })
      await responseFor(A.page, '/api/posts/' + aPost + '/image', 'PUT', () => A.page.getByRole('button', { name: '画像を保存', exact: true }).click(), 415)
      expect((await api(A, '/api/posts/' + aPost)).body.image.id).toBe(prior)
      await A.page.getByRole('button', { name: '選択を取り消す', exact: true }).click()
    })

    await step('E10', async () => {
      // Complete desktop/mobile screen coverage without allocating more identities.
      for (const width of [1280, 375]) {
        await A.page.setViewportSize({ width, height: width === 375 ? 812 : 800 })
        for (const [hash, screen] of [['#', 'following'], ['#timeline/all', 'all'], ['#profile', 'profile-self'], ['#profile/' + B.username, 'profile-other'], ['#profile-edit', 'profile-edit'], ['#search', 'search-empty'], ['#record-new', 'record-new'], ['#record-edit/' + aPost, 'record-edit'], ['#record/' + aPost, 'record-detail']]) {
          await go(A.page, hash); await scan(A.page, `${screen}-${width}`)
        }
        await responseFor(A.page, '/api/users/search', 'GET', () => go(A.page, '#search'), 200)
        for (const [query, screen] of [[`fl10a_${runId}_missing`, 'search-zero'], [B.username, 'search-result']]) {
          await A.page.getByLabel('ユーザー名・表示名', { exact: true }).fill(query)
          await responseFor(A.page, '/api/users/search', 'GET', () => A.page.getByRole('button', { name: '検索', exact: true }).click(), 200)
          if (screen === 'search-zero') await expect(A.page.getByText('ユーザーが見つかりません。', { exact: true })).toBeVisible()
          else await expect(A.page.getByRole('link', { name: B.name, exact: true })).toBeVisible()
          await scan(A.page, `${screen}-${width}`)
        }
      }
      mark('keyboard')
      await go(A.page, '#')
      await keyboardTarget(A.page, A.page.getByRole('link', { name: 'トレーニングを記録する', exact: true }), true)
      await keyboardTarget(A.page, A.page.getByLabel('種目名', { exact: true }))
      await A.page.keyboard.type('Keyboard exercise')
      await keyboardTarget(A.page, A.page.getByLabel('種目1 セット1 重量（kg）', { exact: true })); await A.page.keyboard.type('20')
      await keyboardTarget(A.page, A.page.getByLabel('種目1 セット1 回数', { exact: true })); await A.page.keyboard.type('5')
      await keyboardTarget(A.page, A.page.getByRole('button', { name: /＋ セットを追加/ }), true)
      await keyboardTarget(A.page, A.page.getByLabel('種目1 セット2 重量（kg）', { exact: true })); await A.page.keyboard.type('30')
      await keyboardTarget(A.page, A.page.getByLabel('種目1 セット2 回数', { exact: true })); await A.page.keyboard.type('6')
      await keyboardTarget(A.page, A.page.getByLabel('メモ', { exact: true })); await A.page.keyboard.type(`keyboard ${runId}`)
      budget.take('posts')
      const saved = await responseFor(A.page, '/api/posts', 'POST', () => keyboardTarget(A.page, A.page.getByRole('button', { name: '記録する', exact: true }), true), 201)
      const keyboardRecord = await saved.json()
      const id = keyboardRecord.id as string; resources.posts.push({ id, actor: A })
      expect(keyboardRecord.note).toBe(`keyboard ${runId}`)
      expect(keyboardRecord.exercises[0].name).toBe('Keyboard exercise')
      expect(keyboardRecord.exercises[0].sets.map((row: { weight_kg: string; reps: number }) => [Number(row.weight_kg), row.reps])).toEqual([[20, 5], [30, 6]])
      await keyboardTarget(A.page, A.page.getByRole('textbox', { name: 'コメント本文', exact: true })); await A.page.keyboard.type(`keyboard comment ${runId}`); budget.take('comments')
      const sent = await responseFor(A.page, '/api/posts/' + id + '/comments', 'POST', () => keyboardTarget(A.page, A.page.getByRole('button', { name: 'コメントする', exact: true }), true), 201)
      resources.comments.push((await sent.json()).comment.id)
      await keyboardTarget(A.page, A.page.getByRole('button', { name: '記録を削除', exact: true }), true)
      await scan(A.page, 'delete-dialog-mobile')
      await expect(A.page.getByRole('alertdialog', { name: '記録の削除確認' }).getByRole('button', { name: 'キャンセル', exact: true })).toBeFocused()
      const modal = A.page.getByRole('alertdialog', { name: '記録の削除確認' })
      // Native dialogs may include browser chrome in the cycle (W3C H102).
      // Exercise both boundaries and reject focus on any background page control.
      for (const key of ['Tab', 'Tab', 'Tab', 'Shift+Tab', 'Shift+Tab', 'Shift+Tab']) {
        await A.page.keyboard.press(key)
        expect(await modal.evaluate(modalFocusContained)).toBe(true)
      }
      await keyboardTarget(A.page, modal.getByRole('button', { name: 'キャンセル', exact: true }))
      await A.page.keyboard.press('Enter')
      await expect(A.page.getByRole('button', { name: '記録を削除', exact: true })).toBeFocused()
      await A.page.keyboard.press('Enter')
      await keyboardTarget(A.page, A.page.getByRole('alertdialog').getByRole('button', { name: '削除する', exact: true }))
      await responseFor(A.page, '/api/posts/' + id, 'DELETE', () => A.page.keyboard.press('Enter'), 204)
      resources.posts = resources.posts.filter(row => row.id !== id); resources.comments = []
      await deletionSettled(A.page, recoveryLog)
      const serious = audit.flatMap(row => row.violations as { impact: string }[]).filter(row => row.impact === 'serious' || row.impact === 'critical')
      expect(serious.length).toBe(0)
      expect(audit.every(row => row.overflow_px <= 1)).toBe(true)
    })

    await step('E08', async () => {
      const passed = await recoveryCases({
        network: { ready: () => sessionMatches(B, recoveryLog, 'B'), action: () => networkRecovery(B, noteB, recoveryLog) },
        csrf: { ready: () => sessionMatches(A, recoveryLog, 'A'), action: () => recoveryLog.stage('case-csrf', A.page, 'A', async () => {
          const rejected = await api(A, '/api/posts/' + aPost, 'PUT', recordPayload, false)
          expect(rejected.status).toBe(403); expect(rejected.body.code).toBe('CSRF_FAILED')
          expect((await api(A, '/api/posts/' + aPost)).body.note).toBe(noteEdited)
        }) },
        'old-session': { ready: () => sessionMatches(A, recoveryLog, 'A'), action: () => recoveryLog.stage('case-old-session', A.page, 'A', async () => {
          const old = await guardedContext(browser, { storageState: await A.context.storageState() })
          try {
            const tab = await guardedPage(A.context)
            try { await tab.goto(ORIGIN); await logout({ ...A, page: tab }) }
            finally { await tab.close() }
            const response = await old.request.get(ORIGIN + '/api/auth/me', { maxRedirects: 0 })
            expect(response.status()).toBe(401); expect((await response.json()).code).toBe('AUTH_REQUIRED')
          } finally { await old.close() }
          await A.page.reload(); await login(A)
        }) },
        'cookie-loss': { ready: () => sessionMatches(A, recoveryLog, 'A'), action: () => recoveryLog.stage('case-cookie-loss', A.page, 'A', async () => {
          const oldForLogout = await guardedContext(browser, { storageState: await A.context.storageState() })
          try {
            await A.context.clearCookies({ name: 'sessionid' })
            await A.page.reload(); await expect(A.page.getByRole('button', { name: 'ログイン', exact: true })).toBeVisible()
            const csrf = (await (await oldForLogout.request.get(ORIGIN + '/api/auth/csrf', { maxRedirects: 0 })).json()).csrf_token
            expect((await oldForLogout.request.post(ORIGIN + '/api/auth/logout', { headers: { 'X-CSRFToken': csrf }, maxRedirects: 0 })).status()).toBe(204)
          } finally { await oldForLogout.close() }
          await login(A)
        }) },
      }, recovery, save)
      if (!passed) throw new Error('CASE_FAILED')
    }).catch(() => { failed = true })

    // No continuation based only on a caught error: re-establish live identities
    // and the exact owned resource. A timeout/closed context cannot pass this gate.
    let continuationReady = false
    try {
      await A.context.setOffline(false); await B.context.setOffline(false)
      if (await sessionMatches(A, recoveryLog, 'A') && await sessionMatches(B, recoveryLog, 'B')) {
        const owned = await api(A, '/api/posts/' + aPost)
        continuationReady = owned.status === 200 && owned.body.id === aPost && owned.body.viewer_id === A.id && owned.body.is_owner === true && owned.body.note === noteEdited
      }
      recoveryLog.event('postcondition', A.page, 'A', 'observation', { matches: continuationReady })
    } catch { continuationReady = false }
    if (!continuationReady) throw new Error('PRECONDITION_FAILED')

    // Capture has its own outcome: a recording failure must not hide otherwise
    // independent recovery/deletion observations. The whole run still fails.
    if (process.env.FITLOG_E2E_CAPTURE === '1') {
      try {
        await withinCancellableDeadline((scope: CancellationScope) => capture(browser, A, B, aPost, mark, scope), 300_000)
        captureStatus = 'pass'
      }
      catch (error) {
        if (error instanceof Error && error.message === 'CASE_TIMEOUT') unconfirmedWritesOnTimeout = true
        captureStatus = 'fail'; failed = true; failures.push(sanitizeFailure(error))
      }
      finally { save() }
    }

    await step('E09', async () => {
      await openPost(A, aPost)
      await A.page.getByRole('button', { name: '記録を削除', exact: true }).click()
      await responseFor(A.page, '/api/posts/' + aPost, 'DELETE', () => A.page.getByRole('alertdialog').getByRole('button', { name: '削除する', exact: true }).click(), 204)
      resources.posts = resources.posts.filter(row => row.id !== aPost)
      expect((await api(B, '/api/posts/' + aPost)).status).toBe(404)
      await go(A.page, '#'); await expect(A.page.getByText(noteEdited, { exact: true })).toHaveCount(0)
    })
  } catch {
    failed = true
  } finally {
    for (const actor of [a, b]) {
      if (!actor) continue
      if (!actor.id) { cleanup.push({ action: 'registration-not-confirmed', status: 'not_run' }); await actor.context.close(); continue }
      try {
        await actor.context.setOffline(false)
        await actor.page.goto(ORIGIN)
        if (await actor.page.getByRole('button', { name: 'ログイン', exact: true }).isVisible()) await login(actor)
        if (actor === b && a?.id) {
          await go(actor.page, '#profile/' + a.username)
          if (await actor.page.getByRole('button', { name: 'フォローを解除', exact: true }).isVisible()) {
            await responseFor(actor.page, '/api/users/' + a.id + '/follow', 'DELETE', () => actor.page.getByRole('button', { name: 'フォローを解除', exact: true }).click(), 200)
          }
        }
        for (const post of resources.posts.filter(row => row.actor === actor)) {
          await go(actor.page, '#record/' + post.id)
          await actor.page.getByRole('button', { name: '記録を削除', exact: true }).click()
          await responseFor(actor.page, '/api/posts/' + post.id, 'DELETE', () => actor.page.getByRole('alertdialog').getByRole('button', { name: '削除する', exact: true }).click(), 204)
          resources.posts = resources.posts.filter(row => row.id !== post.id)
        }
        await go(actor.page, '#profile')
        if (await actor.page.getByRole('button', { name: '画像を削除', exact: true }).isVisible()) {
          await actor.page.getByRole('button', { name: '画像を削除', exact: true }).click()
          await responseFor(actor.page, '/api/users/me/avatar', 'DELETE', () => actor.page.getByRole('alertdialog').getByRole('button', { name: '削除する', exact: true }).click(), 204)
        }
        await logout(actor); await actor.page.reload()
        await expect(actor.page.getByRole('button', { name: 'ログイン', exact: true })).toBeVisible()
        cleanup.push({ action: actor === a ? 'A-owned-ui-cleanup' : 'B-owned-ui-cleanup', status: 'pass' })
      } catch { cleanup.push({ action: actor === a ? 'A-owned-ui-cleanup' : 'B-owned-ui-cleanup', status: 'fail' }); failed = true }
      finally { await actor.context.close() }
    }
    save()
  }
  // Fixed error prevents framework-generated error context from containing inputs.
  if (failed || !ledger.success) throw new Error('E2E_ASSERTION_OR_CLEANUP_FAILED')
})

async function capture(browser: Browser, a: Actor, b: Actor, postId: string, mark: (id: string) => void, scope: CancellationScope) {
  const directory = path.join(artifact, 'videos-quarantine')
  mkdirSync(directory, { recursive: true, mode: 0o700 })
  for (const actor of [a, b]) {
    scope.check()
    mark(actor === a ? 'capture-A' : 'capture-B')
    let unsafe = false
    await scope.using(async () => {
      const storageState = await scope.step(() => actor.context.storageState())
      return guardedContext(browser, { storageState, recordVideo: { dir: directory, size: { width: 1280, height: 800 } } })
    }, async (context: BrowserContext) => {
      // Empty search legitimately lists all members. Hide rows before first paint
      // and reveal only after an exact synthetic query and rendered-row check.
      await scope.step(() => context.addInitScript(() => {
        const install = () => {
          if (!document.documentElement) return
          const style = document.createElement('style')
          style.id = 'fitlog-capture-privacy'
          style.textContent = '.user-results { visibility: hidden !important; }'
          document.documentElement.append(style)
          observer.disconnect()
        }
        const observer = new MutationObserver(install)
        observer.observe(document, { childList: true, subtree: true })
        install()
      }))
      const page: Page = await scope.step(() => guardedPage(context))
      const filmed = { ...actor, context, page }
      const allowed = new Set(['', '#', '#search', '#profile', '#profile/' + a.username, '#profile/' + b.username, '#record/' + postId, '#record-edit/' + postId])
      page.on('framenavigated', frame => { if (frame === page.mainFrame() && frame.url() !== 'about:blank' && !allowed.has(new URL(frame.url()).hash)) unsafe = true })
      await scope.step(() => go(page, '#profile'))
      await scope.step(() => expect(page.getByRole('heading', { name: actor.name, exact: true })).toBeVisible())
      await scope.step(() => go(page, '#record/' + postId))
      await scope.step(() => expect(page.locator('article.workout-card')).toBeVisible())
      if (actor === a) {
        await scope.step(() => go(page, '#record-edit/' + postId))
        await scope.step(() => page.getByLabel('メモ', { exact: true }).fill(`Edited ${runId}`))
        await scope.step(() => responseFor(page, '/api/posts/' + postId, 'PUT', () => page.getByRole('button', { name: '変更を保存', exact: true }).click(), 200))
      } else {
        // The exact synthetic username cannot expose a broad shared user list.
        const preflight = await scope.step(() => api(filmed, '/api/users/search?q=' + encodeURIComponent(a.username)))
        expect(captureSearchAllowed(a, a.username, preflight.body.items)).toBe(true)
        const maskEffective = await scope.step(() => page.evaluate(() => {
          const probe = document.createElement('ul'); probe.className = 'user-results'
          document.body.append(probe)
          const hidden = getComputedStyle(probe).visibility === 'hidden'
          probe.remove()
          return hidden
        }))
        expect(maskEffective).toBe(true)
        await scope.step(() => responseFor(page, '/api/users/search', 'GET', () => go(page, '#search'), 200))
        await scope.step(() => page.getByLabel('ユーザー名・表示名', { exact: true }).fill(a.username))
        const exact = await scope.step(() => responseFor(page, '/api/users/search', 'GET', () => page.getByRole('button', { name: '検索', exact: true }).click(), 200))
        const exactBody = await scope.step(() => exact.json())
        expect(captureSearchAllowed(a, new URL(exact.url()).searchParams.get('q'), exactBody.items)).toBe(true)
        await scope.step(() => expect(page.locator('.user-results > li')).toHaveCount(1))
        const maskedLink = page.locator('.user-results > li > a')
        await scope.step(() => expect(maskedLink).toHaveText(a.name))
        await scope.step(() => expect(maskedLink).toHaveAttribute('href', '#profile/' + encodeURIComponent(a.username)))
        await scope.step(() => page.locator('#fitlog-capture-privacy').evaluate(element => element.remove()))
        await scope.step(() => page.getByRole('link', { name: a.name, exact: true }).click())
        await scope.step(() => responseFor(page, '/api/users/' + a.id + '/follow', 'POST', () => page.getByRole('button', { name: 'フォローする', exact: true }).click(), 200))
        await scope.step(() => go(page, '#'))
        await scope.step(() => page.locator('article.workout-card').filter({ hasText: `Edited ${runId}` }).getByRole('link', { name: '記録の詳細', exact: true }).click())
        await scope.step(() => responseFor(page, '/api/posts/' + postId + '/like', 'POST', () => page.getByRole('button', { name: 'いいね', exact: true }).click(), 200))
        budget.take('comments')
        await scope.step(() => page.getByRole('textbox', { name: 'コメント本文', exact: true }).fill(`capture ${runId}`))
        const sent = await scope.step(() => responseFor(page, '/api/posts/' + postId + '/comments', 'POST', () => page.getByRole('button', { name: 'コメントする', exact: true }).click(), 201))
        const commentId = (await scope.step(() => sent.json())).comment.id
        await scope.step(() => page.reload())
        await scope.step(() => page.locator('article.comment-row').getByRole('button', { name: '削除', exact: true }).click())
        await scope.step(() => responseFor(page, '/api/comments/' + commentId, 'DELETE', () => page.getByRole('button', { name: 'コメントを削除する', exact: true }).click(), 204))
        await scope.step(() => responseFor(page, '/api/posts/' + postId + '/like', 'DELETE', () => page.getByRole('button', { name: 'いいね', exact: true }).click(), 200))
        await scope.step(() => go(page, '#profile/' + a.username))
        await scope.step(() => responseFor(page, '/api/users/' + a.id + '/follow', 'DELETE', () => page.getByRole('button', { name: 'フォローを解除', exact: true }).click(), 200))
      }
      await scope.step(() => page.reload())
      if (await scope.step(() => page.getByLabel('メールアドレス', { exact: true }).isVisible())) unsafe = true
    })
    if (unsafe) throw new Error('CAPTURE_QUARANTINED')
  }
  scope.check()
  writeFileSync(path.join(artifact, 'capture-safe.json'), JSON.stringify({ status: 'local_capture_pending_playback', authentication: 'not_recorded', search_privacy_mask: 'until_exact_synthetic_result', public_sharing: 'not_authorized' }))
}
