import Hero from '../components/Hero';
import Features from '../components/Features';
import HowItWorks from '../components/HowItWorks';
import Link from 'next/link';

export default function Home() {
  return (
    <main>
      <nav style={{ position: 'absolute', top: 0, width: '100%', zIndex: 10, padding: '1.5rem 0' }}>
        <div className="container" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <div style={{ fontWeight: 'bold', fontSize: '1.25rem', letterSpacing: '-0.02em' }}>
            <span style={{ color: 'var(--accent-primary)' }}>IDE</span> API
          </div>
          <div style={{ display: 'flex', gap: '1.5rem', alignItems: 'center' }}>
            <Link href="#features" style={{ fontSize: '0.9rem', color: 'var(--text-muted)' }}>Features</Link>
            <Link href="/login" style={{ fontSize: '0.9rem' }}>Login</Link>
            <Link href="/signup" className="btn-primary" style={{ padding: '0.5rem 1rem', fontSize: '0.9rem' }}>Get Started</Link>
          </div>
        </div>
      </nav>

      <Hero />
      <Features />
      <HowItWorks />
      
      <section style={{ padding: '8rem 0', textAlign: 'center' }}>
        <div className="container">
          <h2 style={{ fontSize: '3rem', marginBottom: '1.5rem', letterSpacing: '-0.02em' }}>Ready to automate?</h2>
          <p style={{ color: 'var(--text-muted)', fontSize: '1.25rem', marginBottom: '2.5rem', maxWidth: '600px', marginInline: 'auto' }}>
            Join the companies replacing their manual data entry with intelligent, layout-resilient AI workflows.
          </p>
          <Link href="/signup" className="btn-primary" style={{ padding: '1rem 2rem', fontSize: '1.1rem' }}>
            Start Building Free
          </Link>
        </div>
      </section>

      <footer style={{ borderTop: '1px solid var(--border-color)', padding: '3rem 0', marginTop: '4rem' }}>
        <div className="container" style={{ display: 'flex', justifyContent: 'space-between', color: 'var(--text-muted)', fontSize: '0.9rem' }}>
          <div>&copy; {new Date().getFullYear()} Intelligent Data Extraction. All rights reserved.</div>
          <div style={{ display: 'flex', gap: '1.5rem' }}>
            <Link href="/privacy">Privacy</Link>
            <Link href="/terms">Terms</Link>
          </div>
        </div>
      </footer>
    </main>
  );
}
