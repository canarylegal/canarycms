/** Reserved global e-mail precedent for sending a quote with attachment. */
export const QUOTE_EMAIL_PRECEDENT_REFERENCE = 'QUOTE_EMAIL'

export type PendingCaseCompose = {
  kind: 'letter' | 'email'
  preferPrecedentReference?: string
  attachmentFileId?: string
}

export type PrecedentPickerState = {
  kind: 'letter' | 'document' | 'email'
  preferPrecedentReference?: string
  attachmentFileId?: string
}
