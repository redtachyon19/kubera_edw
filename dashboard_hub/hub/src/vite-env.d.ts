/// <reference types="vite/client" />

declare module '@registry' {
  /** One dashboard inside a section, as declared in `dashboard_hub/dashboards.json`. */
  export interface RegistryDashboard {
    id: string;
    title: string;
    module: string;
    /** `stub` has its own Streamlit process; `planned` is a slot with nothing behind it yet. */
    status: 'stub' | 'planned';
    port?: number;
    blurb: string;
    marts: string[];
    planned: string[];
    /** Where the data comes from when a dashboard reads no marts. */
    source?: string;
  }

  /** A top-bar tab, holding the dashboards that belong to it. */
  export interface RegistrySection {
    slug: string;
    name: string;
    accent: string;
    metal: string;
    tagline: string;
    description: string;
    dashboards: RegistryDashboard[];
  }

  export interface RegistryOrg {
    name: string;
    short: string;
    product: string;
    /** Engraved strapline under the masthead. */
    descriptor: string;
    tagline: string;
  }

  const registry: {
    org: RegistryOrg;
    basePrefix: string;
    sections: RegistrySection[];
  };

  export default registry;
}
