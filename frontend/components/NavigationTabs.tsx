// components/NavigationTabs.tsx

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

'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';

type Props = {
  groupId: number;
};

export default function NavigationTabs({ groupId }: Props) {
  const pathname = usePathname();

  const tabs = [
    { name: 'Group Overview', href: `/home/${groupId}` },
    { name: 'Members', href: `/home/${groupId}/members` },
    { name: 'Meetings', href: `/home/${groupId}/meetings` },
  ];

  return (
    <ul className="mb-4 flex flex-wrap text-sm font-medium text-center text-gray-500 border-b border-gray-200 dark:border-gray-700 dark:text-gray-400">
      {tabs.map((tab) => {
        const isActive = pathname === tab.href;
        return (
          <li className="me-2" key={tab.name}>
            <Link href={tab.href}>
              <span
                className={`inline-block p-4 rounded-t-lg hover:text-gray-600 hover:bg-gray-50 dark:hover:bg-gray-800 dark:hover:text-gray-300 ${
                  isActive
                    ? 'text-blue-600 bg-gray-100 active dark:bg-gray-800 dark:text-blue-500'
                    : 'text-blue-600 hover:underline'
                }`}
              >
                {tab.name}
              </span>
            </Link>
          </li>
        );
      })}
    </ul>
  );
}