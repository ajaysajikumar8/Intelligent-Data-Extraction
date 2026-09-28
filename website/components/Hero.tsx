import styles from './Hero.module.css';
import Link from 'next/link';

export default function Hero() {
  return (
    <section className={styles.hero}>
      <div className="container">
        <div className={styles.content}>
          <div className={`animate-fade-in ${styles.badge}`}>
            <span className={styles.badgeDot}></span>
            Intelligent Data Extraction v1.0
          </div>
          
          <h1 className={`animate-fade-in ${styles.title}`}>
            Automate Data Entry with <br />
            <span className="gradient-text">AI Precision</span>
          </h1>
          
          <p className={`animate-fade-in ${styles.subtitle}`}>
            Instantly turn unstructured PDFs, emails, and images into clean, structured JSON. Connect to Zapier, Make, or your custom CRM in seconds.
          </p>
          
          <div className={`animate-fade-in ${styles.actions}`}>
            <Link href="/signup" className="btn-primary">
              Start Building Free
            </Link>
            <Link href="#features" className="btn-secondary">
              See How It Works
            </Link>
          </div>
        </div>

        <div className={`animate-fade-in glass ${styles.mockupContainer}`}>
          <div className={styles.mockupHeader}>
            <div className={styles.mockupDots}>
              <span></span><span></span><span></span>
            </div>
            <div className={styles.mockupTitle}>invoice_extraction_pipeline.json</div>
          </div>
          <div className={styles.mockupBody}>
            <pre className={styles.codeSnippet}>
              <code>
{`{
  "status": "success",
  "document": {
    "type": "invoice",
    "vendor": "Acme Corp",
    "total_amount": 1450.00,
    "line_items": [
      { "description": "Consulting Services", "amount": 1000.00 },
      { "description": "Software License", "amount": 450.00 }
    ]
  }
}`}
              </code>
            </pre>
          </div>
        </div>
      </div>
    </section>
  );
}
