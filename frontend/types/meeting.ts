import {Group} from './group';
import {GroupMember} from './group_member';
export type GroupReference = Pick<Group, 'id' | 'name'>;
export type GroupMemberReference = Pick<GroupMember, 'id' | 'name'>;
export interface Meeting {
  id: number;
  date: string;
  created: string;
  group:GroupReference[];
  attendees:GroupMemberReference[];
}