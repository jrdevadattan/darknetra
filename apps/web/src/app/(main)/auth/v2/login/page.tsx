import { LoginForm } from '@/features/auth/login-form';

export default function LoginV2() {
  return (
    <div className="mx-auto flex w-full max-w-md flex-col justify-center space-y-8 px-6">
      <div className="space-y-2">
        <p className="font-medium text-muted-foreground text-xs uppercase tracking-wider">
          Authorized personnel only
        </p>
        <h1 className="font-semibold text-3xl tracking-tight">Sign in to DARKNETRA</h1>
        <p className="text-muted-foreground text-sm">
          Use the investigator account issued by your administrator. Self-registration is not enabled.
        </p>
      </div>
      <LoginForm />
    </div>
  );
}
