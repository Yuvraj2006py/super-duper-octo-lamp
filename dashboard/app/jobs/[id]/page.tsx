'use client';

import Link from 'next/link';
import { useParams } from 'next/navigation';
import { useEffect, useMemo, useState } from 'react';

import { getJob, listApplications } from '../../../lib/api';

export default function JobDetailPage() {
  const params = useParams<{ id: string }>();
  const jobId = String(params.id || '');

  const [job, setJob] = useState<any>(null);
  const [applications, setApplications] = useState<any[]>([]);
  const [error, setError] = useState('');

  const appForJob = useMemo(
    () => applications.find((app) => app.job_id === jobId),
    [applications, jobId]
  );

  async function load() {
    try {
      const [jobData, appData] = await Promise.all([getJob(jobId), listApplications()]);
      setJob(jobData);
      setApplications(appData);
      setError('');
    } catch (err: unknown) {
      setError(String(err));
    }
  }

  useEffect(() => {
    if (!jobId) return;
    const interval = setInterval(load, 10000);
    load();
    return () => clearInterval(interval);
  }, [jobId]);

  if (!job) {
    return <main style={{ padding: 20 }}>Loading...</main>;
  }

  const drafts = job.raw_payload?.drafts || {};
  const questionAnswerPairs = drafts.question_answer_pairs || [];

  return (
    <main style={{ maxWidth: 1000, margin: '20px auto', fontFamily: 'sans-serif' }}>
      <p>
        <Link href="/">Back</Link>
      </p>
      <h1>{job.title || 'Untitled Job'}</h1>
      <p>
        {job.company || '-'} | {job.location || '-'} | Status: {job.status}
      </p>

      {error && <p style={{ color: 'crimson' }}>{error}</p>}

      <section style={{ marginBottom: 20 }}>
        <h3>Score Breakdown</h3>
        <pre>{JSON.stringify(job.score_breakdown || {}, null, 2)}</pre>
      </section>

      <section style={{ marginBottom: 20 }}>
        <h3>Generated Drafts</h3>
        <p><strong>Resume Summary</strong></p>
        <pre>{drafts.resume_summary || 'No draft yet.'}</pre>
        <p><strong>Cover Letter</strong></p>
        <pre>{drafts.cover_letter || 'No draft yet.'}</pre>
      </section>

      <section style={{ marginBottom: 20 }}>
        <h3>Application Q&A</h3>
        {questionAnswerPairs.length === 0 ? (
          <p>No application questions detected for this posting.</p>
        ) : (
          questionAnswerPairs.map((pair: any, idx: number) => (
            <div key={`${pair.key || idx}`} style={{ marginBottom: 12 }}>
              <p><strong>Q:</strong> {pair.question}</p>
              <pre>{pair.answer}</pre>
            </div>
          ))
        )}
      </section>

      <section style={{ marginBottom: 20 }}>
        <h3>Verification Report</h3>
        <pre>{JSON.stringify(appForJob?.verification_report || {}, null, 2)}</pre>
      </section>

      {appForJob ? (
        <p>
          Automation mode: verified applications are auto-approved and packet build runs without manual review.
        </p>
      ) : (
        <p>No application record yet.</p>
      )}
    </main>
  );
}
