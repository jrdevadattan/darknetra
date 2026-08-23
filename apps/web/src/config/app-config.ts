import packageJson from '../../package.json';

const currentYear = new Date().getFullYear();

export const APP_CONFIG = {
  name: 'DARKNETRA',
  version: packageJson.version,
  copyright: `© ${currentYear}, DARKNETRA.`,
  meta: {
    title: 'DARKNETRA — Investigator Intelligence Dashboard',
    description:
      'DARKNETRA is an evidence-first investigator dashboard for authorized narcotics intelligence, evidence review, cross-platform correlation, and explainable analysis.',
  },
};
