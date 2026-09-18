import type {ReactNode} from 'react';
import Layout from '@theme/Layout';
import Heading from '@theme/Heading';
import Link from '@docusaurus/Link';
import styles from './resources.module.css';

type Asset = {
  title: string;
  blurb: string;
  meta: string;
  links: {label: string; href: string}[];
};

const ASSETS: Asset[] = [
  {
    title: 'Install',
    blurb: 'h2kvm 1.2.1 on PyPI. GuestKit is installed with it.',
    meta: 'pip install "h2kvm==1.2.1"',
    links: [
      {label: 'PyPI', href: 'https://pypi.org/project/h2kvm/1.2.1/'},
      {label: 'Quickstart', href: '/docs/getting-started/quickstart'},
    ],
  },
  {
    title: 'Source',
    blurb: 'The converter, the operator, and the docs live in one repository.',
    meta: 'github.com/zyvorai/h2kvm',
    links: [
      {label: 'GitHub', href: 'https://github.com/zyvorai/h2kvm'},
      {
        label: 'Changelog',
        href: 'https://github.com/zyvorai/h2kvm/blob/main/CHANGELOG.md',
      },
    ],
  },
  {
    title: 'VDDK was never the exit',
    blurb:
      'The counter to The Register, 10 September 2026. The disk leaves through the vSphere API. The guest is fixed before power-on.',
    meta: 'Article',
    links: [
      {
        label: 'Read on GitHub',
        href: 'https://github.com/zyvorai/h2kvm/blob/main/docs/marketing/vddk-was-never-the-exit.md',
      },
      {label: 'How it works', href: '/docs/how-it-works'},
    ],
  },
  {
    title: 'Product',
    blurb:
      'GuestKit, h2kvm, Zorvia, Zeus OS, and Machina on zyvor.dev. Book a demo or start a 30-day proof of concept.',
    meta: 'zyvor.dev',
    links: [
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
];

function AssetCard({asset}: {asset: Asset}) {
  return (
    <article className={styles.card}>
      <Heading as="h2" className={styles.cardTitle}>
        {asset.title}
      </Heading>
      <p className={styles.meta}>{asset.meta}</p>
      <p className={styles.blurb}>{asset.blurb}</p>
      <div className={styles.actions}>
        {asset.links.map((link) =>
          link.href.startsWith('/') ? (
            <Link
              key={link.href}
              className="button button--primary button--sm"
              to={link.href}>
              {link.label}
            </Link>
          ) : (
            <a
              key={link.href}
              className="button button--primary button--sm"
              href={link.href}>
              {link.label}
            </a>
          ),
        )}
      </div>
    </article>
  );
}

export default function Resources(): ReactNode {
  return (
    <Layout
      title="Resources"
      description="Install h2kvm, read the source, and book a demo.">
      <main className="container margin-vert--lg">
        <header className={styles.header}>
          <Heading as="h1">Resources</Heading>
          <p className={styles.lead}>
            Install, source, and the buyer path. For the convert command, see
            the{' '}
            <Link to="/docs/getting-started/quickstart">quickstart</Link>.
          </p>
        </header>
        <div className={styles.grid}>
          {ASSETS.map((asset) => (
            <AssetCard key={asset.title} asset={asset} />
          ))}
        </div>
        <p className={styles.note}>
          Questions? <a href="mailto:sales@zyvor.dev">sales@zyvor.dev</a>
          {' · '}
          <a href="https://zyvor.dev/h2kvm">zyvor.dev/h2kvm</a>
        </p>
      </main>
    </Layout>
  );
}
