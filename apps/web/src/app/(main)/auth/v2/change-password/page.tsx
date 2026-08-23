import { ChangePasswordForm } from '@/features/auth/change-password-form';

export default function ChangePasswordPage() {
  return (
    <div className="mx-auto flex w-full max-w-md flex-col justify-center space-y-8 px-6">
      <div className="space-y-2">
        <p className="font-medium text-muted-foreground text-xs uppercase tracking-wider">
          Password change required
        </p>
        <h1 className="font-semibold text-3xl tracking-tight">Secure your investigator account</h1>
        <p className="text-muted-foreground text-sm">
          This session cannot enter the investigator workspace until a new password is set.
        </p>
      </div>
      <ChangePasswordForm />
    </div>
  );
}
