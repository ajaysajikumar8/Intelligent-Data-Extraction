import { Link } from 'react-router-dom'
import { ArrowLeft, FileQuestion } from 'lucide-react'
import { Button } from '../components/ui/Button'
import styles from './NotFound.module.css'

export function NotFound() {
  return (
    <div className={styles.page}>
      <FileQuestion size={64} className={styles.icon} />
      <h1 className={styles.title}>Page Not Found</h1>
      <p className={styles.sub}>
        The page you're looking for doesn't exist or has been moved.
      </p>
      <Link to="/dashboard">
        <Button variant="secondary">
          <ArrowLeft size={15} /> Back to Dashboard
        </Button>
      </Link>
    </div>
  )
}
