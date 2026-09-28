import styles from './Skeleton.module.css'

interface SkeletonProps {
  width?: string | number
  height?: string | number
  borderRadius?: string
  className?: string
}

export function Skeleton({
  width = '100%',
  height = 16,
  borderRadius,
  className,
}: SkeletonProps) {
  return (
    <span
      className={[styles.skeleton, className ?? ''].filter(Boolean).join(' ')}
      style={{
        width,
        height,
        borderRadius: borderRadius ?? 'var(--radius-sm)',
      }}
      aria-hidden="true"
    />
  )
}

/** Pre-built skeleton for a table row */
export function SkeletonRow({ cols = 5 }: { cols?: number }) {
  return (
    <tr className={styles.row}>
      {Array.from({ length: cols }).map((_, i) => (
        <td key={i} style={{ padding: '12px 16px' }}>
          <Skeleton height={14} width={i === 0 ? '40%' : '70%'} />
        </td>
      ))}
    </tr>
  )
}

/** Pre-built skeleton card */
export function SkeletonCard() {
  return (
    <div className={styles.card}>
      <Skeleton height={12} width="40%" />
      <Skeleton height={32} width="60%" />
      <Skeleton height={12} width="30%" />
    </div>
  )
}
