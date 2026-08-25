"use client";

import type { FormEvent } from "react";
import { useId, useState } from "react";
import { PlusIcon } from "lucide-react";

import { AsyncState } from "@/components/darknetra/async-state";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Field, FieldError, FieldGroup, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { ApiError } from "@/lib/api/errors";

import { CasesTable } from "./cases-table";
import { useCases, useCreateCase } from "./queries";
import type { CaseSensitivity } from "./types";

const initialForm = {
  caseCode: "",
  title: "",
  sensitivity: "STANDARD" as CaseSensitivity,
  sourceAuthority: "",
};

function CreateCaseDialog() {
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState(initialForm);
  const createCase = useCreateCase();
  const id = useId();

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    await createCase.mutateAsync({
      case_code: form.caseCode.trim().toUpperCase(),
      title: form.title.trim(),
      sensitivity: form.sensitivity,
      source_authority_summary: form.sourceAuthority.trim(),
    });
    setForm(initialForm);
    setOpen(false);
  }

  const errorMessage = createCase.error instanceof Error ? createCase.error.message : null;

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button type="button">
          <PlusIcon />
          New case
        </Button>
      </DialogTrigger>
      <DialogContent className="sm:max-w-lg">
        <form className="space-y-4" onSubmit={handleSubmit}>
          <DialogHeader>
            <DialogTitle>Create case</DialogTitle>
            <DialogDescription>Add an authorized case to the live investigator inventory.</DialogDescription>
          </DialogHeader>
          <FieldGroup>
            <Field>
              <FieldLabel htmlFor={`${id}-case-code`}>Case code</FieldLabel>
              <Input
                id={`${id}-case-code`}
                autoComplete="off"
                maxLength={40}
                pattern="[A-Z0-9]+(?:-[A-Z0-9]+)*"
                placeholder="DARKNETRA-001"
                required
                value={form.caseCode}
                onChange={(event) => setForm((current) => ({ ...current, caseCode: event.target.value }))}
              />
            </Field>
            <Field>
              <FieldLabel htmlFor={`${id}-title`}>Title</FieldLabel>
              <Input
                id={`${id}-title`}
                autoComplete="off"
                maxLength={200}
                minLength={3}
                required
                value={form.title}
                onChange={(event) => setForm((current) => ({ ...current, title: event.target.value }))}
              />
            </Field>
            <Field>
              <FieldLabel htmlFor={`${id}-sensitivity`}>Sensitivity</FieldLabel>
              <select
                id={`${id}-sensitivity`}
                className="h-9 rounded-md border bg-background px-3 text-sm"
                required
                value={form.sensitivity}
                onChange={(event) =>
                  setForm((current) => ({ ...current, sensitivity: event.target.value as CaseSensitivity }))
                }
              >
                <option value="STANDARD">Standard</option>
                <option value="RESTRICTED">Restricted</option>
              </select>
            </Field>
            <Field>
              <FieldLabel htmlFor={`${id}-source-authority`}>Source authority</FieldLabel>
              <Textarea
                id={`${id}-source-authority`}
                maxLength={500}
                minLength={1}
                placeholder="Authorized case material received under court order"
                required
                value={form.sourceAuthority}
                onChange={(event) => setForm((current) => ({ ...current, sourceAuthority: event.target.value }))}
              />
            </Field>
            {errorMessage ? <FieldError>{errorMessage}</FieldError> : null}
          </FieldGroup>
          <DialogFooter>
            <Button type="submit" disabled={createCase.isPending}>
              {createCase.isPending ? "Creating..." : "Create case"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

export function CasesLiveView() {
  const casesQuery = useCases({ limit: 100, offset: 0 });

  if (casesQuery.isPending) {
    return <AsyncState state="loading" />;
  }

  if (casesQuery.isError) {
    if (casesQuery.error instanceof ApiError && casesQuery.error.status === 0) {
      return (
        <AsyncState
          state="offline"
          title="Case service offline"
          description="The case API could not be reached. Substitute case records are not displayed."
        />
      );
    }

    if (casesQuery.error instanceof ApiError && (casesQuery.error.status === 401 || casesQuery.error.status === 403)) {
      return (
        <AsyncState
          state="error"
          title="Case access denied"
          description="This session is not authorized to list cases."
        />
      );
    }

    return (
      <AsyncState
        state="error"
        title="Cases unavailable"
        description="The visible case list could not be loaded from the API."
      />
    );
  }

  return (
    <div className="space-y-4">
      <div className="flex justify-end">
        <CreateCaseDialog />
      </div>
      {casesQuery.isFetching ? (
        <AsyncState
          state="stale"
          title="Refreshing cases"
          description="Showing the last successful case list while a fresh response is requested."
        />
      ) : null}
      {casesQuery.data.hasMore ? (
        <AsyncState
          state="partial"
          title="Case list truncated"
          description="Showing the first 100 visible cases. Use search and filters to narrow the active inventory."
        />
      ) : null}
      {casesQuery.data.items.length === 0 ? (
        <AsyncState
          state="empty"
          title="No visible cases"
          description="No cases are currently visible to this authenticated user."
        />
      ) : (
        <CasesTable cases={casesQuery.data.items} />
      )}
    </div>
  );
}
