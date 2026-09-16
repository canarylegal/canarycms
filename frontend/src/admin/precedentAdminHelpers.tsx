export function suggestedPrecedentReferenceHex(): string {
  try {
    const a = new Uint8Array(3)
    crypto.getRandomValues(a)
    return Array.from(a, (b) => b.toString(16).padStart(2, '0')).join('')
  } catch {
    return Array.from({ length: 6 }, () => Math.floor(Math.random() * 16).toString(16)).join('')
  }
}

export function PrecedentNamePencilIcon() {
  return (
    <svg
      width="16"
      height="16"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden
    >
      <path d="M12 20h9" />
      <path d="M16.5 3.5a2.121 2.121 0 0 1 3 3L7 19l-4 1 1-4 12.5-12.5z" />
    </svg>
  )
}

export function precedentDisplayNameFromFile(file: File): string {
  const stem = file.name.replace(/\.docx$/i, '').trim()
  return stem || file.name
}
