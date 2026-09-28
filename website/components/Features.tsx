import styles from './Features.module.css';

export default function Features() {
  const features = [
    {
      title: 'Universal Webhooks',
      description: 'Plug and play with Zapier, Make, or custom CRM webhooks. No-code integrations are built in from day one.',
      icon: '⚡',
    },
    {
      title: 'Resilient AI Extraction',
      description: 'Forget brittle OCR templates. Our Gemini-powered engine understands intent, so it never breaks when layouts change.',
      icon: '🧠',
    },
    {
      title: 'Human-in-the-Loop',
      description: 'Review low-confidence extractions before they hit your database. Maintain 100% data integrity.',
      icon: '👁️',
    },
    {
      title: 'Multi-Modal Inputs',
      description: 'Forward an email with an attachment, or upload a JSON payload. The pipeline handles everything seamlessly.',
      icon: '📩',
    }
  ];

  return (
    <section id="features" className={styles.featuresSection}>
      <div className="container">
        <div className={styles.header}>
          <h2 className={styles.title}>Extraction that actually works</h2>
          <p className={styles.subtitle}>
            Built to solve the real problems of data entry, without the headache of legacy OCR.
          </p>
        </div>

        <div className={styles.grid}>
          {features.map((feature, idx) => (
            <div key={idx} className={`glass ${styles.card}`}>
              <div className={styles.iconWrapper}>{feature.icon}</div>
              <h3 className={styles.cardTitle}>{feature.title}</h3>
              <p className={styles.cardDesc}>{feature.description}</p>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
