'use client';

import { useState } from 'react';

import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useRouter } from 'next/navigation';

import { Button } from '@/components/ui/button';
import { Field, FieldError, FieldGroup, FieldLabel } from '@/components/ui/field';
import { Input } from '@/components/ui/input';
import { changePassword } from '@/lib/api/auth';
import { ApiError } from '@/lib/api/errors';
import { queryKeys } from '@/lib/query/keys';

import { LogoutButton } from './session-controls';

function passwordErrorMessage(error: unknown): string {
  if (error instanceof ApiError && error.status === 422) {
    if (
      error.details &&
      typeof error.details === 'object' &&
      'detail' in error.details &&
      typeof error.details.detail === 'string'
    ) {
      return error.details.detail;
    }
    return 'The new password does not meet the password policy.';
  }
  if (error instanceof ApiError && error.status === 0) {
    return 'Password service unavailable.';
  }
  return 'Unable to update the password.';
}

export function ChangePasswordForm() {
  const router = useRouter();
  const queryClient = useQueryClient();
  const [newPassword, setNewPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [formError, setFormError] = useState<string | null>(null);
  const changeMutation = useMutation({
    mutationFn: (password: string) => changePassword({ newPassword: password }),
  });

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setFormError(null);

    if (newPassword !== confirmPassword) {
      setNewPassword('');
      setConfirmPassword('');
      setFormError('Passwords do not match.');
      return;
    }

    try {
      const user = await changeMutation.mutateAsync(newPassword);
      setNewPassword('');
      setConfirmPassword('');
      queryClient.setQueryData(queryKeys.auth.me, user);
      router.replace('/dashboard');
      router.refresh();
    } catch (error) {
      setNewPassword('');
      setConfirmPassword('');
      setFormError(passwordErrorMessage(error));
    }
  }

  return (
    <div className="space-y-4">
      <form noValidate onSubmit={handleSubmit} className="flex flex-col gap-4">
        <FieldGroup className="gap-4">
          <Field className="gap-1.5">
            <FieldLabel htmlFor="darknetra-new-password">New password</FieldLabel>
            <Input
              id="darknetra-new-password"
              name="new-password"
              type="password"
              autoComplete="new-password"
              minLength={12}
              maxLength={128}
              value={newPassword}
              onChange={(event) => setNewPassword(event.target.value)}
              disabled={changeMutation.isPending}
              required
            />
          </Field>
          <Field className="gap-1.5">
            <FieldLabel htmlFor="darknetra-confirm-password">Confirm new password</FieldLabel>
            <Input
              id="darknetra-confirm-password"
              name="confirm-password"
              type="password"
              autoComplete="new-password"
              minLength={12}
              maxLength={128}
              value={confirmPassword}
              onChange={(event) => setConfirmPassword(event.target.value)}
              disabled={changeMutation.isPending}
              required
            />
          </Field>
        </FieldGroup>
        <p className="text-muted-foreground text-xs">
          Use 12–128 characters. The password must not equal the username.
        </p>
        {formError ? <FieldError role="alert">{formError}</FieldError> : null}
        <Button type="submit" disabled={changeMutation.isPending}>
          {changeMutation.isPending ? 'Updating password…' : 'Update password'}
        </Button>
      </form>
      <div className="flex items-center justify-between gap-3 border-t pt-4">
        <p className="text-muted-foreground text-xs">You can sign out without changing the password.</p>
        <LogoutButton />
      </div>
    </div>
  );
}
