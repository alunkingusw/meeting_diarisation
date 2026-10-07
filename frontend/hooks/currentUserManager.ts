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

import { useCallback, useState } from 'react';
import { User } from '@/types/user';
import { authenticatedFetch, SessionExpiredError } from '@/lib/auth';

export function useCurrentUser() {
  const [currentUser, setCurrentUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchCurrentUser = useCallback(async (signal?: AbortSignal) => {
    setLoading(true);
    setError(null);
    try {
      const res = await authenticatedFetch(`${process.env.NEXT_PUBLIC_API_URL}/users/me`, { signal });
      if (!res.ok) throw new Error(`Unable to load your account (HTTP ${res.status}).`);
      setCurrentUser(await res.json());
    } catch (err) {
      if (signal?.aborted) return;
      if (!(err instanceof SessionExpiredError)) console.error(err);
      setCurrentUser(null);
      setError(err instanceof Error ? err.message : 'Unable to load your account.');
    } finally {
      if (!signal?.aborted) setLoading(false);
    }
  }, []);

  return { currentUser, loading, error, fetchCurrentUser };
}
