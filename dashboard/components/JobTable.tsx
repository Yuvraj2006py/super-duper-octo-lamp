'use client';

import Link from 'next/link';

export type JobRow = {
  id: string;
  title?: string;
  company?: string;
  location?: string;
  status: string;
  score_total?: number;
};

export function JobTable({ jobs }: { jobs: JobRow[] }) {
  return (
    <table style={{ width: '100%', borderCollapse: 'collapse' }}>
      <thead>
        <tr>
          <th style={{ textAlign: 'left' }}>Title</th>
          <th style={{ textAlign: 'left' }}>Company</th>
          <th style={{ textAlign: 'left' }}>Location</th>
          <th style={{ textAlign: 'left' }}>Score</th>
          <th style={{ textAlign: 'left' }}>Status</th>
        </tr>
      </thead>
      <tbody>
        {jobs.map((job) => (
          <tr key={job.id}>
            <td>
              <Link href={`/jobs/${job.id}`}>{job.title || job.id}</Link>
            </td>
            <td>{job.company || '-'}</td>
            <td>{job.location || '-'}</td>
            <td>{typeof job.score_total === 'number' ? job.score_total.toFixed(3) : '-'}</td>
            <td>{job.status}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
