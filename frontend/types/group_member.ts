import {Group} from './group';
export type GroupReference = Pick<Group, 'id' | 'name'>;
export interface GroupMember {
  id: number;
  name: string;
  created: string;
  group:GroupReference;
}