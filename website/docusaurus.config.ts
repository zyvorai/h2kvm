import {themes as prismThemes} from 'prism-react-renderer';
import type {Config} from '@docusaurus/types';
import type * as Preset from '@docusaurus/preset-classic';

const config: Config = {
  title: 'h2kvm',
  tagline: 'Any hypervisor to KVM. The guest is fixed before power-on.',
  favicon: 'img/favicon.svg',

  future: {
    v4: true,
  },

  url: 'https://zyvorai.github.io',
  baseUrl: '/h2kvm/',

  organizationName: 'zyvorai',
  projectName: 'h2kvm',

  onBrokenLinks: 'throw',

  markdown: {
    hooks: {
      onBrokenMarkdownLinks: 'warn',
    },
  },

  i18n: {
    defaultLocale: 'en',
    locales: ['en'],
  },

  // Screenshots and share cards stay in the repo root. README and this site
  // both use the same files.
  staticDirectories: [
    'static',
    '../docs/client-presentations/screenshots',
    '../docs/social',
  ],

  presets: [
    [
      'classic',
      {
        docs: {
          sidebarPath: './sidebars.ts',
          editUrl: 'https://github.com/zyvorai/h2kvm/tree/main/website/',
        },
        blog: false,
        theme: {
          customCss: './src/css/custom.css',
        },
      } satisfies Preset.Options,
    ],
  ],

  themeConfig: {
    image: 'h2kvm-share-card.png',
    colorMode: {
      respectPrefersColorScheme: true,
    },
    navbar: {
      title: 'h2kvm',
      logo: {
        alt: 'h2kvm',
        src: 'img/favicon.svg',
      },
      items: [
        {
          type: 'docSidebar',
          sidebarId: 'docsSidebar',
          position: 'left',
          label: 'Docs',
        },
        {
          to: '/resources',
          label: 'Resources',
          position: 'left',
        },
        {
          href: 'https://github.com/zyvorai/h2kvm',
          label: 'GitHub',
          position: 'right',
        },
        {
          href: 'https://zyvor.dev/h2kvm',
          label: 'Enterprise',
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
            {label: 'Quickstart', to: '/docs/getting-started/quickstart'},
            {label: 'How it works', to: '/docs/how-it-works'},
            {label: 'Resources', to: '/resources'},
          ],
        },
        {
          title: 'Project',
          items: [
            {label: 'GitHub', href: 'https://github.com/zyvorai/h2kvm'},
            {label: 'PyPI', href: 'https://pypi.org/project/h2kvm/'},
            {
              label: 'Changelog',
              href: 'https://github.com/zyvorai/h2kvm/blob/main/CHANGELOG.md',
            },
          ],
        },
        {
          title: 'Zyvor Enterprise',
          items: [
            {label: 'zyvor.dev/h2kvm', href: 'https://zyvor.dev/h2kvm'},
            {
              label: 'Book a demo',
              href: 'https://zyvor.dev/contact?intent=demo&utm_source=github&utm_medium=h2kvm&utm_campaign=docs_site',
            },
            {
              label: '30-day PoC',
              href: 'https://zyvor.dev/poc?utm_source=github&utm_medium=h2kvm&utm_campaign=docs_site',
            },
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
