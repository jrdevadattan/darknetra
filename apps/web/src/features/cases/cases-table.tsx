'use client';

import { useMemo, useState } from 'react';
import Link from 'next/link';

import { SourceClassBadge } from '@/components/darknetra/source-class-badge';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import type { CaseStatus, CaseSummary } from './types';

const PAGE_SIZE = 4;

function CaseStatusBadge({ status }: { status: CaseStatus }) {
  return <Badge variant={status === 'CLOSED' ? 'outline' : 'secondary'}>{status}</Badge>;
}

export function CasesTable({ cases }: { cases: CaseSummary[] }) {
  const [query, setQuery] = useState('');
  const [status, setStatus] = useState('ALL');
  const [sensitivity, setSensitivity] = useState('ALL');
  const [sort, setSort] = useState('updated-desc');
  const [page, setPage] = useState(1);

  const filtered = useMemo(() => {
    const normalized = query.trim().toLowerCase();
    const result = cases.filter((item) => {
      const matchesQuery =
        !normalized ||
        [item.id, item.title, item.owner].some((value) => value.toLowerCase().includes(normalized));
      const matchesStatus = status === 'ALL' || item.status === status;
      const matchesSensitivity = sensitivity === 'ALL' || item.sensitivity === sensitivity;
      return matchesQuery && matchesStatus && matchesSensitivity;
    });

    return [...result].sort((a, b) => {
      if (sort === 'title-asc') return a.title.localeCompare(b.title);
      if (sort === 'alerts-desc') return b.openAlerts - a.openAlerts;
      return Date.parse(b.updatedAt) - Date.parse(a.updatedAt);
    });
  }, [cases, query, sensitivity, sort, status]);

  const pageCount = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE));
  const safePage = Math.min(page, pageCount);
  const visible = filtered.slice((safePage - 1) * PAGE_SIZE, safePage * PAGE_SIZE);

  const resetPage = () => setPage(1);

  return (
    <div className="space-y-4">
      <div className="grid gap-3 md:grid-cols-4">
        <Input
          aria-label="Search cases"
          placeholder="Search case ID, title, owner…"
          value={query}
          onChange={(event) => {
            setQuery(event.target.value);
            resetPage();
          }}
        />
        <select
          aria-label="Status"
          className="h-9 rounded-md border bg-background px-3 text-sm"
          value={status}
          onChange={(event) => {
            setStatus(event.target.value);
            resetPage();
          }}
        >
          <option value="ALL">All statuses</option>
          <option value="OPEN">Open</option>
          <option value="REVIEW">Review</option>
          <option value="CLOSED">Closed</option>
        </select>
        <select
          aria-label="Sensitivity"
          className="h-9 rounded-md border bg-background px-3 text-sm"
          value={sensitivity}
          onChange={(event) => {
            setSensitivity(event.target.value);
            resetPage();
          }}
        >
          <option value="ALL">All sensitivity</option>
          <option value="STANDARD">Standard</option>
          <option value="RESTRICTED">Restricted</option>
        </select>
        <select
          aria-label="Sort"
          className="h-9 rounded-md border bg-background px-3 text-sm"
          value={sort}
          onChange={(event) => setSort(event.target.value)}
        >
          <option value="updated-desc">Recently updated</option>
          <option value="title-asc">Title A–Z</option>
          <option value="alerts-desc">Open alerts</option>
        </select>
      </div>

      <div className="rounded-xl border">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Case</TableHead>
              <TableHead>Status</TableHead>
              <TableHead>Source class</TableHead>
              <TableHead>Owner</TableHead>
              <TableHead className="text-right">Evidence</TableHead>
              <TableHead className="text-right">Reviews</TableHead>
              <TableHead className="text-right">Alerts</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {visible.length ? (
              visible.map((item) => (
                <TableRow key={item.id}>
                  <TableCell className="min-w-72 whitespace-normal">
                    <Link href={`/cases/${item.id}`} className="font-medium hover:underline">
                      {item.title}
                    </Link>
                    <div className="mt-1 text-muted-foreground text-xs">{item.id}</div>
                  </TableCell>
                  <TableCell><CaseStatusBadge status={item.status} /></TableCell>
                  <TableCell><SourceClassBadge sourceClass={item.sourceClass} /></TableCell>
                  <TableCell>{item.owner}</TableCell>
                  <TableCell className="text-right tabular-nums">{item.evidenceCount}</TableCell>
                  <TableCell className="text-right tabular-nums">{item.pendingReviews}</TableCell>
                  <TableCell className="text-right tabular-nums">{item.openAlerts}</TableCell>
                </TableRow>
              ))
            ) : (
              <TableRow>
                <TableCell colSpan={7} className="h-24 text-center text-muted-foreground">
                  No cases match the current filters.
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      </div>

      <div className="flex items-center justify-between gap-3 text-sm">
        <span className="text-muted-foreground">
          {filtered.length} case{filtered.length === 1 ? '' : 's'} · Page {safePage} of {pageCount}
        </span>
        <div className="flex gap-2">
          <Button
            type="button"
            variant="outline"
            size="sm"
            disabled={safePage <= 1}
            onClick={() => setPage((current) => Math.max(1, current - 1))}
          >
            Previous
          </Button>
          <Button
            type="button"
            variant="outline"
            size="sm"
            disabled={safePage >= pageCount}
            onClick={() => setPage((current) => Math.min(pageCount, current + 1))}
          >
            Next
          </Button>
        </div>
      </div>
    </div>
  );
}
