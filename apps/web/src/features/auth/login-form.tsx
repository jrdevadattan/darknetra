'use client';

import { useState } from 'react';

import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useRouter } from 'next/navigation';

import { Button } from '@/components/ui/button';
import { Field, FieldError, FieldGroup, FieldLabel } from '@/components/ui/field';
import { Input } from '@/components/ui/input';
import { login } from '@/lib/api/auth';
import { ApiError } from '@/lib/api/errors';
import { queryKeys } from '@/lib/query/keys';

function loginErrorMessage(error: unknown): string {
  if (error instanceof ApiError && (error.status === 401 || error.status === 429)) {
    return 'Unable to sign in with those credentials.';
  }
  if (error instanceof ApiError && error.status === 0) {
    return 'Sign-in service unavailable.';
  }
  return 'Unable to sign in right now.';
}

export function LoginForm() {
  const router = useRouter();
  const queryClient = useQueryClient();
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [formError, setFormError] = useState<string | null>(null);
  const loginMutation = useMutation({
    mutationFn: (credentials: { username: string; password: string }) =>
      login(credentials.username, credentials.password),
  });

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setFormError(null);

    try {
      const response = await loginMutation.mutateAsync({ username, password });
      setPassword('');
      queryClient.setQueryData(queryKeys.auth.me, response.user);
      router.replace(
        response.user.must_change_password ? '/auth/v2/change-password' : '/dashboard',
      );
      router.refresh();
    } catch (error) {
      setPassword('');
      setFormError(loginErrorMessage(error));
    }
  }

  return (
    <form noValidate onSubmit={handleSubmit} className="flex flex-col gap-4">
      <FieldGroup className="gap-4">
        <Field className="gap-1.5">
          <FieldLabel htmlFor="darknetra-login-username">Username</FieldLabel>
          <Input
            id="darknetra-login-username"
            name="username"
            type="text"
            autoComplete="username"
            value={username}
            onChange={(event) => setUsername(event.target.value)}
            disabled={loginMutation.isPending}
            required
          />
        </Field>
        <Field className="gap-1.5">
          <FieldLabel htmlFor="darknetra-login-password">Password</FieldLabel>
          <Input
            id="darknetra-login-password"
            name="password"
            type="password"
            autoComplete="current-password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            disabled={loginMutation.isPending}
            required
          />
        </Field>
      </FieldGroup>
      {formError ? <FieldError role="alert">{formError}</FieldError> : null}
      <Button type="submit" className="w-full" disabled={loginMutation.isPending}>
        {loginMutation.isPending ? 'Signing in…' : 'Sign in'}
      </Button>
    </form>
  );
}
