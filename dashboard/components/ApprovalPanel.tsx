'use client';

import { useState } from 'react';

import { approveApplication, rejectApplication } from '../lib/api';

export function ApprovalPanel({ applicationId }: { applicationId: string }) {
  const [reason, setReason] = useState('MVP review');
  const [message, setMessage] = useState('');

  return (
    <div style={{ border: '1px solid #ccc', padding: 12, borderRadius: 6 }}>
      <h3>Approval Gate</h3>
      <input value={reason} onChange={(e) => setReason(e.target.value)} style={{ width: '100%' }} />
      <div style={{ display: 'flex', gap: 8, marginTop: 8 }}>
        <button
          onClick={async () => {
            try {
              const result = await approveApplication(applicationId, reason);
              setMessage(`Approved. Packet status: ${result.packet_status}`);
            } catch (err: unknown) {
              setMessage(String(err));
            }
          }}
        >
          Approve + Build Packet
        </button>
        <button
          onClick={async () => {
            try {
              const result = await rejectApplication(applicationId, reason);
              setMessage(`Rejected: ${result.status}`);
            } catch (err: unknown) {
              setMessage(String(err));
            }
          }}
        >
          Reject
        </button>
      </div>
      <p>{message}</p>
    </div>
  );
}
