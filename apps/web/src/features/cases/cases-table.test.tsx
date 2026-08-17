import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';

import { CasesTable } from './cases-table';
import { FIXTURE_CASES } from './fixtures';

describe('CasesTable', () => {
  it('supports visible search and links rows to a case', async () => {
    const user = userEvent.setup();
    render(<CasesTable cases={FIXTURE_CASES} />);

    expect(screen.getByRole('textbox', { name: /search cases/i })).toBeInTheDocument();
    expect(screen.getByRole('combobox', { name: /status/i })).toBeInTheDocument();
    expect(screen.getByRole('combobox', { name: /sensitivity/i })).toBeInTheDocument();
    expect(screen.getByRole('combobox', { name: /sort/i })).toBeInTheDocument();

    await user.type(screen.getByRole('textbox', { name: /search cases/i }), 'SYN-DEMO-004');
    expect(screen.getByRole('link', { name: /Image reuse hard-negative/i })).toHaveAttribute(
      'href',
      '/cases/SYN-DEMO-004',
    );
    expect(screen.queryByText('Alias correlation training case')).not.toBeInTheDocument();
  });
});
