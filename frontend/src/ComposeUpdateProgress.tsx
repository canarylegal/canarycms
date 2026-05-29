import { useEffect, useRef } from 'react'
import type { AdminDeployComposeJobOut } from './types'

type ComposePhase = 'git' | 'build' | 'up'

export function formatComposeElapsed(seconds: number | null | undefined): string {
  if (seconds == null || !Number.isFinite(seconds)) return '0:00'
  const s = Math.max(0, Math.floor(seconds))
  const h = Math.floor(s / 3600)
  const m = Math.floor((s % 3600) / 60)
  const r = s % 60
  if (h > 0) {
    return `${h}:${m.toString().padStart(2, '0')}:${r.toString().padStart(2, '0')}`
  }
  return `${m}:${r.toString().padStart(2, '0')}`
}

function stepDone(journal: string[], prefix: string): boolean {
  return journal.some((line) => line.startsWith(prefix) && line.includes('finished'))
}

function barPercent(phase: ComposePhase | null | undefined): number {
  if (phase === 'git') return 18
  if (phase === 'build') return 48
  if (phase === 'up') return 82
  return 8
}

type StepState = 'pending' | 'active' | 'done' | 'skipped'

function stepStatus(
  id: ComposePhase,
  phase: ComposePhase | null | undefined,
  journal: string[],
  hasGit: boolean,
): StepState {
  if (id === 'git') {
    if (!hasGit) return 'skipped'
    if (stepDone(journal, 'git:')) return 'done'
    if (phase === 'git') return 'active'
    return 'pending'
  }
  if (id === 'build') {
    if (stepDone(journal, 'docker-compose: build')) return 'done'
    if (phase === 'build') return 'active'
    if (phase === 'up') return 'done'
    return 'pending'
  }
  if (stepDone(journal, 'docker-compose: up') || stepDone(journal, 'docker compose up')) return 'done'
  if (phase === 'up') return 'active'
  return 'pending'
}

const STEPS: { id: ComposePhase; label: string }[] = [
  { id: 'git', label: 'Git sync' },
  { id: 'build', label: 'Build images' },
  { id: 'up', label: 'Start containers' },
]

export function ComposeUpdateProgress({ progress }: { progress: AdminDeployComposeJobOut | null }) {
  const logRef = useRef<HTMLPreElement>(null)

  useEffect(() => {
    const el = logRef.current
    if (el) el.scrollTop = el.scrollHeight
  }, [progress?.journal_lines?.length])

  if (!progress || progress.status !== 'running') return null

  const journal = progress.journal_lines ?? []
  const phase = progress.progress_phase
  const hasGit = journal.some((line) => line.startsWith('git:'))
  const indeterminate = phase === 'build'
  const pct = barPercent(phase)

  return (
    <div
      className="compose-update-progress"
      style={{
        marginTop: 16,
        padding: 14,
        borderRadius: 8,
        border: '1px solid var(--border, #e4e4e7)',
        background: 'var(--surface-2, #fafafa)',
      }}
    >
      <style>{`
        @keyframes compose-bar-indeterminate {
          0% { transform: translateX(-100%); }
          100% { transform: translateX(250%); }
        }
        .compose-update-progress__bar-indeterminate {
          position: absolute;
          inset: 0;
          width: 40%;
          background: linear-gradient(90deg, transparent, var(--accent, #2563eb), transparent);
          animation: compose-bar-indeterminate 1.4s ease-in-out infinite;
        }
      `}</style>

      <div className="row" style={{ justifyContent: 'space-between', alignItems: 'center', marginBottom: 10 }}>
        <strong style={{ fontSize: 14 }}>Compose update in progress</strong>
        <span className="muted" style={{ fontSize: 13, fontVariantNumeric: 'tabular-nums' }}>
          Elapsed {formatComposeElapsed(progress.elapsed_seconds)}
        </span>
      </div>

      <div
        style={{
          position: 'relative',
          height: 8,
          borderRadius: 4,
          background: 'var(--surface-3, #e4e4e7)',
          overflow: 'hidden',
          marginBottom: 14,
        }}
        aria-hidden
      >
        <div
          style={{
            position: 'absolute',
            left: 0,
            top: 0,
            bottom: 0,
            width: `${pct}%`,
            borderRadius: 4,
            background: 'var(--accent, #2563eb)',
            transition: indeterminate ? 'none' : 'width 0.4s ease',
            opacity: indeterminate ? 0.35 : 1,
          }}
        />
        {indeterminate ? <div className="compose-update-progress__bar-indeterminate" /> : null}
      </div>

      <ol
        style={{
          listStyle: 'none',
          margin: '0 0 12px',
          padding: 0,
          display: 'flex',
          flexWrap: 'wrap',
          gap: '8px 16px',
          fontSize: 13,
        }}
      >
        {STEPS.map(({ id, label }) => {
          const state = stepStatus(id, phase, journal, hasGit)
          const color =
            state === 'active'
              ? 'var(--accent, #2563eb)'
              : state === 'done'
                ? 'var(--success, #15803d)'
                : state === 'skipped'
                  ? 'var(--muted, #71717a)'
                  : 'var(--text-muted, #a1a1aa)'
          const marker =
            state === 'done' ? '✓' : state === 'active' ? '…' : state === 'skipped' ? '—' : '○'
          return (
            <li key={id} style={{ color, fontWeight: state === 'active' ? 600 : 400 }}>
              <span style={{ marginRight: 6 }}>{marker}</span>
              {label}
              {state === 'skipped' ? ' (skipped)' : null}
            </li>
          )
        })}
      </ol>

      {journal.length > 0 ? (
        <pre
          ref={logRef}
          style={{
            margin: 0,
            maxHeight: 160,
            overflow: 'auto',
            fontSize: 12,
            lineHeight: 1.45,
            padding: 10,
            background: 'var(--surface, #fff)',
            borderRadius: 6,
            border: '1px solid var(--border, #e4e4e7)',
            whiteSpace: 'pre-wrap',
            wordBreak: 'break-word',
          }}
        >
          {journal.join('\n')}
        </pre>
      ) : (
        <p className="muted" style={{ margin: 0, fontSize: 13 }}>
          Waiting for first log line…
        </p>
      )}
    </div>
  )
}
