import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';

const rows = [
  ['ADMIN', 'Yes', 'Yes', 'Yes', 'Yes', 'Yes'],
  ['CASE_OWNER', 'No', 'Yes', 'Scoped', 'Yes', 'Scoped'],
  ['COLLECTOR', 'No', 'Assigned', 'Upload', 'No', 'No'],
  ['ANALYST', 'No', 'Assigned', 'Review', 'Analyze', 'No'],
  ['REVIEWER', 'No', 'Assigned', 'Read', 'Review', 'Scoped'],
  ['AUDITOR', 'No', 'Assigned', 'Integrity', 'Read', 'Yes'],
  ['VIEWER', 'No', 'Assigned', 'Redacted', 'Read', 'No'],
] as const;

export function RoleMatrix() {
  return (
    <div className="rounded-xl border">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Role</TableHead>
            <TableHead>Admin</TableHead>
            <TableHead>Case access</TableHead>
            <TableHead>Evidence</TableHead>
            <TableHead>Analysis</TableHead>
            <TableHead>Audit</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {rows.map((row) => (
            <TableRow key={row[0]}>{row.map((cell) => <TableCell key={cell}>{cell}</TableCell>)}</TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}
