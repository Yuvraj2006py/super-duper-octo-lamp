export const API_BASE = process.env.NEXT_PUBLIC_API_BASE || 'http://localhost:8000';

function getToken(): string {
  if (typeof window === 'undefined') {
    return '';
  }
  return localStorage.getItem('job_assistant_token') || '';
}

async function request(path: string, init: RequestInit = {}) {
  const token = getToken();
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
  };
  const initialHeaders = new Headers(init.headers);
  initialHeaders.forEach((value, key) => {
    headers[key] = value;
  });

  if (token) {
    headers.Authorization = `Bearer ${token}`;
  }

  const res = await fetch(`${API_BASE}${path}`, { ...init, headers, cache: 'no-store' });
  if (!res.ok) {
    const txt = await res.text();
    throw new Error(`API ${path} failed: ${res.status} ${txt}`);
  }
  return res.json();
}

export async function login(apiKey: string) {
  return request('/auth/login', {
    method: 'POST',
    body: JSON.stringify({ api_key: apiKey })
  });
}

export async function listJobs() {
  return request('/jobs');
}

export async function getJob(jobId: string) {
  return request(`/jobs/${jobId}`);
}

export async function runPipeline(topN = 3) {
  return request('/pipeline/run', {
    method: 'POST',
    body: JSON.stringify({ top_n: topN, status_filter: 'DISCOVERED', dry_run: false })
  });
}

export async function listApplications() {
  return request('/applications');
}

export async function approveApplication(id: string, reason: string) {
  return request(`/applications/${id}/approve`, {
    method: 'POST',
    body: JSON.stringify({ reason })
  });
}

export async function rejectApplication(id: string, reason: string) {
  return request(`/applications/${id}/reject`, {
    method: 'POST',
    body: JSON.stringify({ reason })
  });
}

export async function listArtifacts(id: string) {
  return request(`/applications/${id}/artifacts`);
}
