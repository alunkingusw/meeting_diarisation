// app/home/[id]/meetings/page.tsx

/*
 * Copyright 2025 Alun King
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *     http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */

'use client'; // Required for using client-side hooks like useEffect and useRouter
import Link from 'next/link';
import { useEffect, useState } from 'react';
import { useParams } from 'next/navigation';
import { useGroupManager } from '@/hooks/groupManager';
import NavigationTabs from '@/components/NavigationTabs';
import GroupLoadState from '@/components/GroupLoadState';

export default function GroupPage() {
  const { id } = useParams(); // Extract the group ID from the URL (/home/[id])
  const {loading, getGroup, updateGroupNotify, updateGroupProjectExpiry, group, error} = useGroupManager();
  const [savingNotify, setSavingNotify] = useState(false);
  const [notifyError, setNotifyError] = useState<string | null>(null);
  const [notifySaved, setNotifySaved] = useState(false);
  const [projectExpiry, setProjectExpiry] = useState('');
  const [savingExpiry, setSavingExpiry] = useState(false);
  const [expiryError, setExpiryError] = useState<string | null>(null);
  const [expirySaved, setExpirySaved] = useState(false);

  useEffect(() => {
    const controller = new AbortController();
    getGroup(Number(id), controller.signal);
    return () => controller.abort();
  }, [id, getGroup]);

  useEffect(() => {
    setProjectExpiry(group?.project_expiry ?? '');
  }, [group?.id, group?.project_expiry]);

  if (loading || error || !group) return <GroupLoadState loading={loading} error={error} />;

  const saveNotify = async (notify: boolean) => {
    setSavingNotify(true);
    setNotifyError(null);
    setNotifySaved(false);
    try {
      await updateGroupNotify(notify);
      setNotifySaved(true);
    } catch (err) {
      setNotifyError(err instanceof Error ? err.message : 'Unable to update notification settings.');
    } finally {
      setSavingNotify(false);
    }
  };

  const saveProjectExpiry = async (expiry: string | null) => {
    setSavingExpiry(true);
    setExpiryError(null);
    setExpirySaved(false);
    try {
      await updateGroupProjectExpiry(expiry);
      setProjectExpiry(expiry ?? '');
      setExpirySaved(true);
    } catch (err) {
      setExpiryError(err instanceof Error ? err.message : 'Unable to update project expiry.');
    } finally {
      setSavingExpiry(false);
    }
  };

  // Render group info if successfully fetched
  return (
     <main className="p-6">
      <Link href={`/home`} className="text-blue-500 hover:underline">
          back to groups
        </Link>
      {/* Tabs */}
      <NavigationTabs groupId={Number(id)} />

      {/* Layout */}
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        <section className="rounded-lg bg-white p-5 shadow" aria-labelledby="group-info-title">
          <h2 id="group-info-title" className="text-xl font-semibold text-gray-900">Group Info</h2>
          <dl className="mt-4 divide-y divide-gray-100 text-sm">
            <div className="flex justify-between gap-4 py-3">
              <dt className="text-gray-500">Name</dt>
              <dd className="text-right font-medium text-gray-900">{group.name}</dd>
            </div>
            <div className="flex justify-between gap-4 py-3">
              <dt className="text-gray-500">Group ID</dt>
              <dd className="font-mono text-gray-900">{group.id}</dd>
            </div>
            <div className="flex justify-between gap-4 py-3">
              <dt className="text-gray-500">Created</dt>
              <dd className="text-right text-gray-900">
                {group.created ? new Date(group.created).toLocaleDateString() : 'Not available'}
              </dd>
            </div>
            <div className="flex justify-between gap-4 py-3">
              <dt className="text-gray-500">Members</dt>
              <dd className="text-gray-900">{group.members?.length ?? 0}</dd>
            </div>
          </dl>

          <div className="border-t border-gray-200 py-4">
            <label htmlFor="project-expiry" className="block text-sm font-medium text-gray-900">
              Project expiry
            </label>
            <p className="mt-1 text-xs text-gray-500">
              Optional. Leave blank when the project has no planned end date.
            </p>
            <div className="mt-2 flex flex-wrap items-center gap-2">
              <input
                id="project-expiry"
                type="date"
                value={projectExpiry}
                disabled={savingExpiry}
                onChange={event => {
                  setProjectExpiry(event.currentTarget.value);
                  setExpirySaved(false);
                  setExpiryError(null);
                }}
                aria-describedby="expiry-status"
                className="rounded border border-gray-300 px-3 py-2 text-sm text-gray-900 disabled:bg-gray-100"
              />
              <button
                type="button"
                onClick={() => void saveProjectExpiry(projectExpiry || null)}
                disabled={savingExpiry || projectExpiry === (group.project_expiry ?? '')}
                className="rounded bg-blue-700 px-3 py-2 text-sm font-medium text-white hover:bg-blue-800 disabled:cursor-not-allowed disabled:opacity-50"
              >
                {savingExpiry ? 'Saving…' : 'Save date'}
              </button>
              <button
                type="button"
                onClick={() => void saveProjectExpiry(null)}
                disabled={savingExpiry || !group.project_expiry}
                className="rounded border border-gray-300 px-3 py-2 text-sm text-gray-700 hover:bg-gray-50 disabled:cursor-not-allowed disabled:opacity-50"
              >
                Clear
              </button>
            </div>
            <p id="expiry-status" className="mt-2 min-h-5 text-xs" aria-live="polite">
              {savingExpiry ? 'Saving…' : expiryError ? (
                <span role="alert" className="text-red-700">{expiryError}</span>
              ) : expirySaved ? (
                <span className="text-green-700">Project expiry saved.</span>
              ) : null}
            </p>
          </div>

          <div className="mt-5 border-t border-gray-200 pt-4">
            <label htmlFor="group-notify" className="flex cursor-pointer items-center justify-between gap-4">
              <span>
                <span className="block text-sm font-medium text-gray-900">Summary email notifications</span>
                <span className="mt-1 block text-xs text-gray-500">
                  Email meeting summaries to members with an email address.
                </span>
              </span>
              <span className="flex shrink-0 items-center gap-2">
                <span className="text-xs font-medium text-gray-600">{group.notify ? 'On' : 'Off'}</span>
                <span className="relative inline-flex">
                  <input
                    id="group-notify"
                    type="checkbox"
                    role="switch"
                    checked={group.notify}
                    disabled={savingNotify}
                    onChange={event => void saveNotify(event.currentTarget.checked)}
                    className="peer sr-only"
                    aria-describedby="notify-status"
                  />
                  <span
                    aria-hidden="true"
                    className="h-6 w-11 rounded-full bg-gray-300 transition-colors after:absolute after:left-0.5 after:top-0.5 after:h-5 after:w-5 after:rounded-full after:bg-white after:shadow after:transition-transform peer-checked:bg-blue-600 peer-checked:after:translate-x-5 peer-focus-visible:outline-none peer-focus-visible:ring-2 peer-focus-visible:ring-blue-600 peer-focus-visible:ring-offset-2 peer-disabled:opacity-50"
                  />
                </span>
              </span>
            </label>
            <p id="notify-status" className="mt-2 min-h-5 text-xs" aria-live="polite">
              {savingNotify ? 'Saving…' : notifyError ? (
                <span role="alert" className="text-red-700">{notifyError}</span>
              ) : notifySaved ? (
                <span className="text-green-700">Notification setting saved.</span>
              ) : null}
            </p>
          </div>
        </section>

        <div className="space-y-6 lg:col-span-2">
          <section className="rounded-lg bg-white p-5 shadow" aria-labelledby="project-links-title">
            <h2 id="project-links-title" className="text-xl font-semibold text-gray-900">Project Links</h2>
            <dl className="mt-3 divide-y divide-gray-100 text-sm">
              <div className="flex flex-wrap items-center justify-between gap-2 py-3">
                <dt className="font-medium text-gray-700">GitHub</dt>
                <dd className="text-right">
                  {group.github_repo_url ? (
                    <a href={group.github_repo_url} target="_blank" rel="noreferrer" className="break-all text-blue-700 hover:underline">
                      {group.github_repo_url}
                    </a>
                  ) : <span className="text-gray-500">Not linked</span>}
                  <span className="ml-3 text-xs text-gray-500">
                    {group.github_connected ? 'Connected' : group.github_repo_url ? 'Not connected' : ''}
                  </span>
                </dd>
              </div>
              <div className="flex flex-wrap items-center justify-between gap-2 py-3">
                <dt className="font-medium text-gray-700">Trello</dt>
                <dd className="text-right">
                  {group.trello_board_id ? (
                    <a href={`https://trello.com/b/${encodeURIComponent(group.trello_board_id)}`} target="_blank" rel="noreferrer" className="text-blue-700 hover:underline">
                      Open board
                    </a>
                  ) : <span className="text-gray-500">Not linked</span>}
                  <span className="ml-3 text-xs text-gray-500">
                    {group.trello_connected ? 'Connected' : group.trello_board_id ? 'Not connected' : ''}
                  </span>
                </dd>
              </div>
            </dl>
          </section>

          <section className="rounded-lg bg-white p-5 shadow" aria-labelledby="members-title">
            <h2 id="members-title" className="text-xl font-semibold text-gray-900">Members</h2>
            {group.members?.length ? (
              <ul className="mt-3 divide-y divide-gray-100 text-sm">
                {group.members.map(member => (
                  <li key={member.id} className="py-2 text-gray-800">{member.name}</li>
                ))}
              </ul>
            ) : (
              <p className="mt-3 text-sm text-gray-500">
                No members yet. Go to the members tab to manage members.
              </p>
            )}
          </section>
        </div>
      </div>
    </main>
  );
}
