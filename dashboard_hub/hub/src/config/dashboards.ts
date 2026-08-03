import registry from '@registry';
import type { RegistryDashboard, RegistryOrg, RegistrySection } from '@registry';

export type Dashboard = RegistryDashboard;
export type Section = RegistrySection;
export type Org = RegistryOrg;

export const org: Org = registry.org;
export const sections: Section[] = registry.sections;

/** URL prefix the Vite proxy forwards to the Streamlit dashboards. */
export const basePrefix: string = (registry.basePrefix ?? '/d').replace(/\/$/, '');

export function getSectionBySlug(slug: string | undefined): Section | undefined {
  return slug ? sections.find((section) => section.slug === slug) : undefined;
}

/** Hub routes live under `/s/*` so the `/d/*` proxy never swallows them. */
export function sectionRoute(section: Section): string {
  return `/s/${section.slug}`;
}

export function dashboardRoute(section: Section, dashboard: Dashboard): string {
  return `/s/${section.slug}/${dashboard.id}`;
}

/** Where the spoke is served, or `undefined` when nothing is running behind it yet. */
export function embedPathFor(dashboard: Dashboard): string | undefined {
  return dashboard.status === 'stub' ? `${basePrefix}/${dashboard.id}/` : undefined;
}

export function countLive(section: Section): number {
  return section.dashboards.filter((dashboard) => dashboard.status === 'stub').length;
}

export const totals = {
  dashboards: sections.reduce((sum, section) => sum + section.dashboards.length, 0),
  live: sections.reduce((sum, section) => sum + countLive(section), 0),
};
