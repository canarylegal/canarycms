import type { ReactNode } from 'react'
import type { FeeScaleScopeLevel } from './feeScaleGrouping'

type ThreadRowProps = {
  depth: FeeScaleScopeLevel
  isLast: boolean
  children: ReactNode
}

function FeeScaleThreadRow({ depth, isLast, children }: ThreadRowProps) {
  if (depth === 0) {
    return <div className="feeScaleThreadRow feeScaleThreadRow--root">{children}</div>
  }

  return (
    <div
      className={[
        'feeScaleThreadRow',
        `feeScaleThreadRow--depth${depth}`,
        isLast ? 'feeScaleThreadRow--last' : '',
      ]
        .filter(Boolean)
        .join(' ')}
    >
      <div className="feeScaleThreadGutter" aria-hidden="true">
        <span className="feeScaleThreadVline" />
        <span className="feeScaleThreadElbow" />
      </div>
      <div className="feeScaleThreadContent">{children}</div>
    </div>
  )
}

type ThreadGroupProps = {
  depth: FeeScaleScopeLevel
  label?: string
  children: ReactNode
}

function FeeScaleThreadGroup({ depth, label, children }: ThreadGroupProps) {
  return (
    <div className={`feeScaleThreadGroup feeScaleThreadGroup--depth${depth}`}>
      {label ? <div className="feeScaleThreadGroupLabel">{label}</div> : null}
      <div className="feeScaleThreadGroupItems">{children}</div>
    </div>
  )
}

type ScaleRowListProps = {
  scales: { id: string; render: () => ReactNode }[]
  depth: FeeScaleScopeLevel
}

function FeeScaleScaleRows({ scales, depth }: ScaleRowListProps) {
  return (
    <>
      {scales.map((row, index) => (
        <FeeScaleThreadRow key={row.id} depth={depth} isLast={index === scales.length - 1}>
          {row.render()}
        </FeeScaleThreadRow>
      ))}
    </>
  )
}

export { FeeScaleThreadGroup, FeeScaleScaleRows, FeeScaleThreadRow }
