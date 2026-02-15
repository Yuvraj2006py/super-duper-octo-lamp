import React from 'react';

export const metadata = {
  title: 'Job Application Assistant',
  description: 'MVP dashboard'
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
