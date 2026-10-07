import Link from 'next/link';

export default function GroupLoadState({ loading, error }: { loading: boolean; error: string | null }) {
  if (loading) return <p role="status">Loading group...</p>;
  return (
    <main className="p-6">
      <p role="alert">{error || 'Group not found.'}</p>
      <Link href="/home" className="text-blue-500 hover:underline">Back to groups</Link>
    </main>
  );
}
