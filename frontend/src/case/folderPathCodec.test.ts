import { describe, expect, it } from 'vitest'
import {
  decodeFolderPathForDisplay,
  decodeFolderPathSegment,
  encodeFolderPathSegment,
  joinFolderPath,
  splitFolderPath,
} from './folderPathCodec'

describe('folderPathCodec', () => {
  it('encodes segments so slashes do not nest', () => {
    expect(encodeFolderPathSegment('A/B')).toBe('A%2FB')
    expect(decodeFolderPathSegment('A%2FB')).toBe('A/B')
  })

  it('decodes repeatedly encoded segments up to a safe limit', () => {
    const once = encodeURIComponent('hello world')
    const twice = encodeURIComponent(once)
    expect(decodeFolderPathSegment(twice)).toBe('hello world')
  })

  it('stops decoding on invalid sequences', () => {
    expect(decodeFolderPathSegment('%E0%A4%A')).toBe('%E0%A4%A')
  })

  it('splits and filters empty path parts', () => {
    expect(splitFolderPath('')).toEqual([])
    expect(splitFolderPath('/a//b/')).toEqual(['a', 'b'])
  })

  it('joins a display name under a parent storage path', () => {
    expect(joinFolderPath('', 'Inbox')).toBe('Inbox')
    expect(joinFolderPath('root', 'A/B')).toBe('root/A%2FB')
    expect(joinFolderPath('root', '  ')).toBe('root')
  })

  it('decodes full paths for display breadcrumbs', () => {
    expect(decodeFolderPathForDisplay('root/A%2FB/notes')).toBe('root/A/B/notes')
  })
})
