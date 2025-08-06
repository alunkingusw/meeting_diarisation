// components/NavigationTabs.tsx
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