import type {ReactNode} from 'react';
import clsx from 'clsx';
import Link from '@docusaurus/Link';
import useBaseUrl from '@docusaurus/useBaseUrl';
import Layout from '@theme/Layout';
import Heading from '@theme/Heading';
import FeatureHighlights from '@site/src/components/FeatureHighlights';
import Reveal from '@site/src/components/Reveal';

import styles from './index.module.css';

function HomepageHeader() {
  const dashboard = useBaseUrl('/02-dashboard.png');
  return (
    <header className={clsx('hero hero--primary', styles.heroBanner)}>
      <div className="container">
        <div className={clsx(styles.heroText, 'text--center')}>
          <Heading as="h1" className="hero__title">
            Any hypervisor
            <br />
            to KVM.
          </Heading>
          <p className="hero__subtitle">
            Export, convert, and deploy VMs from VMware, Hyper-V, Nutanix,
            AWS, Azure, and GCP — with offline guest fixes via GuestKit, a
            web control plane, and a Kubernetes-native operator. First-boot
            science for hypervisor exit.
          </p>
          <div className={styles.buttons}>
            <Link
              className="button button--secondary button--lg"
              to="/docs/README">
              Get Started
            </Link>
            <Link
              className="button button--outline button--lg button--secondary"
              to="https://github.com/zyvorai/h2kvm">
              View on GitHub
            </Link>
          </div>
        </div>
      </div>
      <div className={styles.heroMediaWrap}>
        <img
          className={styles.heroMedia}
          src={dashboard}
          alt="h2kweb dashboard — migration jobs, providers, and status"
        />
        <p className={styles.heroMediaCaption}>
          The h2kweb dashboard — a real deployment, not a mockup.
        </p>
      </div>
    </header>
  );
}

function ProblemStatement() {
  return (
    <section className={styles.problem}>
      <div className="container">
        <Reveal className="row">
          <div className="col col--8 col--offset-2 text--center">
            <Heading as="h2" className={styles.sectionHeading}>
              The cutover problem — fixed before power-on
            </Heading>
            <p>
              Hypervisor exit fails when VirtIO is missing, GRUB is wrong,
              or Windows still points at the old hypervisor — after you
              cut over. h2kvm converts the disk offline, runs{' '}
              <Link to="https://github.com/zyvorai/guestkit">GuestKit</Link>{' '}
              repair, and deploys to libvirt / KubeVirt / OpenStack so
              first boot is planned, not guessed.
            </p>
            <p>
              Suite path: HyperSDK export → GuestKit assure →{' '}
              <strong>h2kvm</strong> convert &amp; deploy → Zeus OS day-2.
            </p>
          </div>
        </Reveal>
      </div>
    </section>
  );
}

function TrustBand() {
  return (
    <section className={styles.trust}>
      <div className="container">
        <Reveal className={styles.trustGrid}>
          <div>
            <Heading as="h3" className={styles.sectionHeading}>
              Real, recorded demos
            </Heading>
            <p>
              8+ disk formats, 35+ guest OS supported, across CLI, web, and
              a Kubernetes operator. Terms are set out in this repository's{' '}
              <Link to="https://github.com/zyvorai/h2kvm/blob/main/LICENSE">
                LICENSE
              </Link>{' '}
              file — read it before deploying.
            </p>
            <Link to="/docs/README">Read the full docs →</Link>
          </div>
          <div className={styles.trustBadges}>
            <img
              src="https://img.shields.io/github/v/release/zyvorai/h2kvm?color=F97316"
              alt="Latest release"
            />
            <img
              src="https://img.shields.io/pypi/v/hypersdk-guestkit.svg"
              alt="GuestKit on PyPI"
            />
          </div>
        </Reveal>
      </div>
    </section>
  );
}

function EnterpriseCTA() {
  return (
    <section className={styles.enterprise}>
      <div className="container text--center">
        <Reveal>
          <Heading as="h2" className={styles.sectionHeading}>
            Community, or Enterprise for scale
          </Heading>
          <p className={styles.enterpriseCopy}>
            See the CE vs Enterprise breakdown for what's included at each
            tier, or book a demo / start a 30-day PoC to evaluate h2kvm
            against your own hypervisor exit.
          </p>
          <Link
            className="button button--primary button--lg"
            to="https://zyvor.dev/contact?intent=demo&utm_source=github&utm_medium=h2kvm">
            Book an Enterprise demo
          </Link>
        </Reveal>
      </div>
    </section>
  );
}

export default function Home(): ReactNode {
  return (
    <Layout
      title="h2kvm — any hypervisor to KVM"
      description="Export, convert, and deploy VMs from VMware, Hyper-V, Nutanix, AWS, Azure and GCP to KVM — with offline guest fixes, a web control plane, and a Kubernetes-native operator.">
      <HomepageHeader />
      <main>
        <ProblemStatement />
        <Reveal>
          <FeatureHighlights />
        </Reveal>
        <TrustBand />
        <EnterpriseCTA />
      </main>
    </Layout>
  );
}
