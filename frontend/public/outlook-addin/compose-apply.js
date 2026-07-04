/* global Office */
'use strict'
;(function () {
  const MAX_ATTACH = 25
  const SUBJECT_CASE_TOKEN_RE = /^\[CANARY:([0-9a-f-]{36})\]\s*/i

  /** Strip legacy matter tokens from older add-in builds (never shown to recipients). */
  function parseSubjectCaseToken(subject) {
    const s = String(subject || '')
    const m = SUBJECT_CASE_TOKEN_RE.exec(s)
    if (!m) return { caseId: '', cleanSubject: s }
    return { caseId: String(m[1]), cleanSubject: s.replace(SUBJECT_CASE_TOKEN_RE, '') }
  }

  function stripLegacySubjectToken(subject) {
    return parseSubjectCaseToken(subject).cleanSubject
  }

  /** When a precedent is used, subject should be the matter description, not the precedent title. */
  function resolveComposeSubject(bundle) {
    if (!bundle || typeof bundle !== 'object') return ''
    const matterDesc =
      bundle.matter_description != null ? String(bundle.matter_description).trim() : ''
    const hasPrecedent = !!(
      bundle.precedent_id ||
      bundle.applied_precedent_id ||
      bundle.precedent_applied
    )
    if (hasPrecedent && matterDesc) return matterDesc
    if (bundle.subject != null) return stripLegacySubjectToken(String(bundle.subject))
    return ''
  }

  function officeAsync(fn) {
    return new Promise(function (resolve, reject) {
      try {
        fn(function (result) {
          if (result.status === Office.AsyncResultStatus.Succeeded) {
            resolve(result.value)
            return
          }
          reject(new Error(result.error ? result.error.message : 'Office API failed'))
        })
      } catch (e) {
        reject(e)
      }
    })
  }

  function parseRecipients(toField) {
    const raw = String(toField || '').trim()
    if (!raw) return []
    const parts = raw.split(/[,;]+/).map(function (s) {
      return s.trim()
    }).filter(Boolean)
    const out = []
    for (const part of parts) {
      const m = /^(.+?)\s*<([^>]+)>$/.exec(part)
      if (m) {
        out.push({ displayName: m[1].trim().replace(/^"|"$/g, ''), emailAddress: m[2].trim() })
      } else if (part.indexOf('@') >= 0) {
        out.push({ displayName: '', emailAddress: part })
      }
    }
    return out
  }

  function escapeHtml(text) {
    return String(text || '')
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
  }

  function plainTextToHtml(text) {
    return String(text || '')
      .split(/\r?\n/)
      .map(function (line) {
        return '<div>' + (line ? escapeHtml(line) : '<br>') + '</div>'
      })
      .join('')
  }

  function getComposeTypeAsync(item) {
    return new Promise(function (resolve) {
      if (!item || typeof item.getComposeTypeAsync !== 'function') {
        resolve('newMail')
        return
      }
      item.getComposeTypeAsync(function (r) {
        if (r.status === Office.AsyncResultStatus.Succeeded && r.value && r.value.composeType) {
          resolve(String(r.value.composeType))
          return
        }
        resolve('newMail')
      })
    })
  }

  function getBodyTypeAsync(item) {
    return officeAsync(function (cb) {
      item.body.getTypeAsync(cb)
    }).then(function (bodyType) {
      if (bodyType === Office.MailboxEnums.BodyType.Html) {
        return Office.CoercionType.Html
      }
      return Office.CoercionType.Text
    })
  }

  function setToAsync(item, recipients) {
    if (!recipients.length) return Promise.resolve()
    return officeAsync(function (cb) {
      item.to.setAsync(recipients, { asyncContext: null }, cb)
    })
  }

  function setSubjectAsync(item, subject) {
    return officeAsync(function (cb) {
      item.subject.setAsync(String(subject || ''), { asyncContext: null }, cb)
    })
  }

  /** Prepend merge text so existing body (e.g. signature) is preserved. */
  function prependBodyAsync(item, bodyText) {
    const merge = String(bodyText || '').trim()
    if (!merge) return Promise.resolve()
    return getBodyTypeAsync(item).then(function (coercionType) {
      const prefix =
        coercionType === Office.CoercionType.Html
          ? plainTextToHtml(merge) + '<div><br></div>'
          : merge + '\n\n'
      return officeAsync(function (cb) {
        item.body.prependAsync(prefix, { coercionType: coercionType }, cb)
      })
    })
  }

  function addAttachmentAsync(item, base64, filename) {
    const name = String(filename || 'attachment').trim() || 'attachment'
    return officeAsync(function (cb) {
      item.addFileAttachmentFromBase64Async(base64, name, { isInline: false }, cb)
    })
  }

  /**
   * Apply a ``compose-bundle`` response to the open Outlook compose item.
   * @param {object} bundle
   * @param {{ skipTo?: boolean }} [options]
   */
  async function applyComposeBundle(bundle, options) {
    const item = Office.context.mailbox.item
    if (!item) {
      throw new Error('Open a compose message first, then open the Canary pane.')
    }

    const skipTo = !!(options && options.skipTo)
    if (!skipTo && bundle && bundle.to) {
      const recipients = parseRecipients(bundle.to)
      if (recipients.length) {
        await setToAsync(item, recipients)
      }
    }
    const resolvedSubject = resolveComposeSubject(bundle)
    if (resolvedSubject || (bundle && bundle.subject != null)) {
      await setSubjectAsync(item, resolvedSubject)
    }
    if (bundle && bundle.body != null) {
      await prependBodyAsync(item, bundle.body)
    }

    const atts = (bundle && bundle.attachments) || []
    let added = 0
    for (let i = 0; i < atts.length && added < MAX_ATTACH; i++) {
      const a = atts[i]
      if (!a || !a.content_base64) continue
      try {
        await addAttachmentAsync(item, a.content_base64, a.filename || 'attachment')
        added += 1
      } catch (_) {
        /* best-effort per attachment */
      }
    }
    if (atts.length && !added) {
      throw new Error('Could not add attachments to the message.')
    }
    return added
  }

  const CANARY_CATEGORY = 'Canary'

  function applyCanaryCategoryAsync(item) {
    return new Promise(function (resolve) {
      if (!item || !item.categories || typeof item.categories.addAsync !== 'function') {
        resolve(false)
        return
      }
      item.categories.addAsync([CANARY_CATEGORY], function (r) {
        if (r.status === Office.AsyncResultStatus.Succeeded) {
          resolve(true)
          return
        }
        const msg = (r.error && r.error.message) || ''
        if (/already|duplicate|same category|in the list/i.test(msg)) {
          resolve(true)
          return
        }
        resolve(false)
      })
    })
  }

  function openNewMessageFromBundle(bundle) {
    return new Promise(function (resolve, reject) {
      if (!Office.context.mailbox || typeof Office.context.mailbox.displayNewMessageForm !== 'function') {
        reject(new Error('This Outlook client cannot open a new compose window automatically.'))
        return
      }
      const params = {}
      if (bundle && bundle.to) {
        const recipients = parseRecipients(bundle.to)
        if (recipients.length) {
          params.toRecipients = recipients.map(function (r) {
            return r.emailAddress
          })
        }
      }
      const resolvedSubject = resolveComposeSubject(bundle)
      if (resolvedSubject) {
        params.subject = resolvedSubject
      }
      const bodyText = String((bundle && bundle.body) || '').trim()
      if (bodyText) {
        params.body = bodyText
      }
      const attachments = []
      const atts = (bundle && bundle.attachments) || []
      for (let i = 0; i < atts.length && attachments.length < MAX_ATTACH; i++) {
        const a = atts[i]
        if (!a || !a.content_base64) continue
        attachments.push({
          type: Office.MailboxEnums.AttachmentType.File,
          name: String(a.filename || 'attachment').trim() || 'attachment',
          inLine: false,
          contentBytes: a.content_base64,
        })
      }
      if (attachments.length) {
        params.attachments = attachments
      }
      try {
        Office.context.mailbox.displayNewMessageForm(params)
        resolve(attachments.length)
      } catch (e) {
        reject(e instanceof Error ? e : new Error('Could not open a new compose window.'))
      }
    })
  }

  globalThis.canaryOutlookApplyCompose = {
    getComposeTypeAsync: getComposeTypeAsync,
    applyComposeBundle: applyComposeBundle,
    applyCanaryCategoryAsync: applyCanaryCategoryAsync,
    openNewMessageFromBundle: openNewMessageFromBundle,
    resolveComposeSubject: resolveComposeSubject,
    parseSubjectCaseToken: parseSubjectCaseToken,
    stripLegacySubjectToken: stripLegacySubjectToken,
  }
})()
