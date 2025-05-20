import {User} from './user'
import {GroupMember} from './group_member'
import {Meeting} from './meeting'

export type UserReference = Pick<User, 'id' | 'username'>;
export interface Group {
  id: number;
  name: string;
  created: string;
  users:UserReference[];
  members:GroupMember[];
  meetings:Meeting[];
}