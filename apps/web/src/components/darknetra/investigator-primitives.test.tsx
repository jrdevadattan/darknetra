import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { AsyncState } from './async-state';
import { MetricLinkCard } from './metric-link-card';
import { SourceClassBadge } from './source-class-badge';
import { StatusBadge } from './status-badge';

describe('investigator primitives', () => {
  it('renders epistemic status as visible text', () => {
    render(<StatusBadge status="pending-review" />);
    expect(screen.getByText('Pending analyst review')).toBeInTheDocument();
  });

  it('renders source class as visible text', () => {
    render(<SourceClassBadge sourceClass="SYNTHETIC" />);
    expect(screen.getByText('SYNTHETIC')).toBeInTheDocument();
  });

  it('makes every metric card a real navigation link', () => {
    render(
      <MetricLinkCard
        label="Pending link reviews"
        value={4}
        description="Requires analyst attention"
        href="/cases?review=pending"
      />,
    );
    expect(screen.getByRole('link', { name: /Pending link reviews/i })).toHaveAttribute(
      'href',
      '/cases?review=pending',
    );
  });

  it.each(['loading', 'empty', 'error', 'partial', 'stale', 'offline'] as const)(
    'exposes %s as a visible state',
    (state) => {
      const { unmount } = render(<AsyncState state={state} />);
      expect(screen.getByTestId(`async-state-${state}`)).toBeInTheDocument();
      unmount();
    },
  );
});
