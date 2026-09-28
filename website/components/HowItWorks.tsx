import styles from './HowItWorks.module.css';

export default function HowItWorks() {
  const steps = [
    {
      step: '01',
      title: 'Send Documents',
      desc: 'Email invoices to your unique inbound webhook address, or upload them via our secure dashboard.',
    },
    {
      step: '02',
      title: 'AI Extracts Data',
      desc: 'Our Gemini-powered engine classifies the document type and extracts all relevant fields into a structured format.',
    },
    {
      step: '03',
      title: 'Webhook Delivery',
      desc: 'The clean JSON payload is automatically sent to your outgoing webhook, triggering your downstream workflows.',
    }
  ];

  return (
    <section className={styles.howItWorksSection}>
      <div className="container">
        <h2 className={styles.sectionTitle}>How it works</h2>
        
        <div className={styles.timeline}>
          {steps.map((s, idx) => (
            <div key={idx} className={styles.step}>
              <div className={styles.stepNumber}>{s.step}</div>
              <div className={`glass ${styles.stepContent}`}>
                <h4 className={styles.stepTitle}>{s.title}</h4>
                <p className={styles.stepDesc}>{s.desc}</p>
              </div>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
