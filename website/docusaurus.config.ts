import {themes as prismThemes} from 'prism-react-renderer';
import type {Config} from '@docusaurus/types';
import type * as Preset from '@docusaurus/preset-classic';

const config: Config = {
  title: 'h2kvm',
  tagline: 'Any hypervisor → KVM. Convert offline. Fix the guest. Deploy with confidence.',
  favicon: 'img/favicon.svg',

  future: {
    v4: true,
  },

  url: 'https://zyvorai.github.io',
  baseUrl: '/h2kvm/',

  organizationName: 'zyvorai',
  projectName: 'h2kvm',

  onBrokenLinks: 'warn',

  markdown: {
    format: 'md',
    hooks: {
      onBrokenMarkdownLinks: 'warn',
    },
  },

  i18n: {
    defaultLocale: 'en',
    locales: ['en'],
  },

  staticDirectories: ['static', '../docs/client-presentations/screenshots'],

  presets: [
    [
      'classic',
      {
        docs: {
          path: '../docs',
          routeBasePath: 'docs',
          sidebarPath: './sidebars.ts',
          editUrl: 'https://github.com/zyvorai/h2kvm/tree/main/docs/',
        },
        blog: false,
        theme: {
          customCss: './src/css/custom.css',
        },
      } satisfies Preset.Options,
    ],
  ],

  themeConfig: {
    colorMode: {
      respectPrefersColorScheme: true,
    },
    navbar: {
      hideOnScroll: false,
      title: 'h2kvm',
      logo: {
        alt: 'h2kvm',
        src: 'img/favicon.svg',
      },
      items: [
        {
          type: 'docSidebar',
          sidebarId: 'docsSidebar',
          position: 'right',
          label: 'Docs',
        },
        {
          href: 'https://github.com/zyvorai/h2kvm',
          label: 'GitHub',
          position: 'right',
        },
      ],
    },
    footer: {
      style: 'dark',
      links: [
        {
          title: 'Docs',
          items: [
            {label: 'Full docs', to: '/docs/README'},
            {label: 'Remote deploy', to: '/docs/deployment/deploy-remote'},
            {label: 'CE vs Enterprise', to: '/docs/ce-vs-enterprise'},
          ],
        },
        {
          title: 'Project',
          items: [
            {label: 'GitHub', href: 'https://github.com/zyvorai/h2kvm'},
            {label: 'Releases', href: 'https://github.com/zyvorai/h2kvm/releases/tag/v1.1.0'},
            {label: 'License', href: 'https://github.com/zyvorai/h2kvm/blob/main/LICENSE'},
          ],
        },
        {
          title: 'Zyvor Enterprise',
          items: [
            {label: 'Book an Enterprise demo', href: 'https://zyvor.dev/contact?intent=demo&utm_source=github&utm_medium=h2kvm'},
            {label: '30-day PoC', href: 'https://zyvor.dev/poc?utm_source=github&utm_medium=h2kvm'},
          ],
        },
      ],
      copyright: `Copyright © ${new Date().getFullYear()} ZyvorAI Labs. See LICENSE for terms.`,
    },
    prism: {
      theme: prismThemes.github,
      darkTheme: prismThemes.dracula,
    },
  } satisfies Preset.ThemeConfig,
};

export default config;
