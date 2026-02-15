'use client';

import { useEffect, useState } from 'react';

import { JobTable } from '../components/JobTable';
import { listJobs, login, runPipeline } from '../lib/api';

export default function HomePage() {
  const [apiKey, setApiKey] = useState('change-me');
  const [jobs, setJobs] = useState<any[]>([]);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  async function loadJobs() {
    try {
      const data = await listJobs();
      setJobs(data);
      setError('');
    } catch (err: unknown) {
      setError(String(err));
    }
  }

  useEffect(() => {
    const interval = setInterval(loadJobs, 10000);
    loadJobs();
    return () => clearInterval(interval);
  }, []);

  return (
    <main style={{ maxWidth: 1100, margin: '20px auto', fontFamily: 'sans-serif' }}>
      <h1>Job Application Assistant MVP</h1>
      <p>Autonomous discovery/ranking/drafting with explicit human approval before packet build.</p>

      <section style={{ marginBottom: 16, display: 'flex', gap: 8 }}>
        <input
          value={apiKey}
          onChange={(e) => setApiKey(e.target.value)}
          placeholder="Local API key"
          style={{ minWidth: 260 }}
        />
        <button
          onClick={async () => {
            try {
              const res = await login(apiKey);
              localStorage.setItem('job_assistant_token', res.token);
              await loadJobs();
            } catch (err: unknown) {
              setError(String(err));
            }
          }}
        >
          Login
        </button>
        <button
          disabled={loading}
          onClick={async () => {
            setLoading(true);
            try {
              await runPipeline(3);
              await loadJobs();
            } catch (err: unknown) {
              setError(String(err));
            } finally {
              setLoading(false);
            }
          }}
        >
          Run Pipeline (Top 3)
        </button>
      </section>

      {error && <p style={{ color: 'crimson' }}>{error}</p>}
      <JobTable jobs={jobs} />
    </main>
  );
}
