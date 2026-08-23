import { redirect } from 'next/navigation';

export default function LoginV1() {
  redirect('/auth/v2/login');
}
