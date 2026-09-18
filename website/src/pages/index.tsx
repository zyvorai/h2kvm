import type {ReactNode} from 'react';
import clsx from 'clsx';
import Link from '@docusaurus/Link';
import useBaseUrl from '@docusaurus/useBaseUrl';
import Layout from '@theme/Layout';
import Heading from '@theme/Heading';
import FeatureHighlights from '@site/src/components/FeatureHighlights';
import ScreenshotStrip from '@site/src/components/ScreenshotStrip';
import Reveal from '@site/src/components/Reveal';

import styles from './index.module.css';

function HomepageHeader() {
  const dashboard = useBaseUrl('/02-dashboard.png');
  return (
    <header className={clsx('hero hero--primary', styles.heroBanner)}>
      <div className="container">
        <div className={styles.heroGrid}>
          <div>
            <Heading as="h1" className="hero__title">
              Any hypervisor
              <br />
              to KVM.
            </Heading>
            <p className="hero__subtitle">
              Convert the disk offline. Fix the guest before power-on. No
              VDDK. Then watch it boot.
            </p>
            <div className={styles.buttons}>
              <Link
                className="button button--secondary button--lg"
                to="/docs/getting-started/quickstart">
                Get Started
              </Link>
              <Link
                className="button button--outline button--lg button--secondary"
                to="/resources">
                Resources
              </Link>
              <Link
                className="button button--outline button--lg button--secondary"
                to="https://github.com/zyvorai/h2kvm">
                View on GitHub
              </Link>
            </div>
          </div>
          <div className={styles.heroMedia}>
            <img
              src={dashboard}
              alt="h2kweb dashboard — migration jobs, providers, and status"
            />
            <p className={styles.heroMediaCaption}>
              Captured against a live lab deployment, not a mockup.
            </p>
          </div>
        </div>
      </div>
    </header>
  );
}

function ArchitectureDiagram() {
  const diagram = useBaseUrl('/h2kvm-vsphere-path.jpg');
  return (
    <section className={styles.diagram}>
      <div className="container">
        <Reveal>
          <p className={styles.eyebrow}>How it talks to vSphere</p>
          <Heading as="h2" className={styles.sectionHeading}>
            HTTPS in. Disk out. No VDDK.
          </Heading>
          <Link to="/docs/how-it-works" className={styles.diagramFrame}>
            <img
              src={diagram}
              alt="h2kvm talks to vCenter over SOAP, then ESXi over an NFC lease. Fallback is HTTPS /folder."
            />
          </Link>
          <p className={styles.diagramLinks}>
            <Link to="/docs/how-it-works">Read how it works</Link>
            <a href="https://zyvor.dev/h2kvm">zyvor.dev/h2kvm</a>
            <a href="https://github.com/zyvorai/h2kvm">github.com/zyvorai/h2kvm</a>
          </p>
        </Reveal>
      </div>
    </section>
  );
}

function ProblemStatement() {
  return (
    <section className={styles.problem}>
      <div className="container">
        <Reveal className="row">
          <div className="col col--8 col--offset-2 text--center">
            <Heading as="h2" className={styles.sectionHeading}>
              The disk leaves. The guest has to boot.
            </Heading>
            <p>
              On 10 September 2026 VMware told The Register the Virtual Disk
              Development Kit was never a license to move VMs. Most
              VMware-to-KVM tools still open disks with that kit. h2kvm does
              not. The disk leaves through the vSphere API and NFS.
            </p>
            <p>
              Copying the disk was never the hard part. First boot fails when
              the bootloader, VirtIO, or Windows still points at the old
              hypervisor. GuestKit repairs that before power-on.
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
              Install it. Then read the license.
            </Heading>
            <p>
              h2kvm 1.2.1 is on PyPI. GuestKit is installed with it. Terms
              are in this repository&apos;s LICENSE — read it before a
              production cutover.
            </p>
            <Link to="/docs/how-it-works">How the path works →</Link>
          </div>
          <div className={styles.trustBadges}>
            <img
              src="https://img.shields.io/pypi/v/h2kvm.svg"
              alt="h2kvm on PyPI"
            />
            <img
              src="https://img.shields.io/github/v/release/zyvorai/h2kvm?color=f97316"
              alt="Latest GitHub release"
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
            Need a cutover, not a lab?
          </Heading>
          <p className={styles.enterpriseCopy}>
            Community proves convert. Enterprise owns the wave: HA, storage
            pipelines, and a support contract. Start with a 30-day proof of
            concept on your estate.
          </p>
          <Link
            className="button button--primary button--lg"
            to="https://zyvor.dev/contact?intent=demo&utm_source=github&utm_medium=h2kvm&utm_campaign=docs_site">
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
      description="Convert VMs from VMware, Hyper-V, Nutanix, AWS, Azure, and GCP to KVM. The guest is fixed before power-on. No VDDK.">
      <HomepageHeader />
      <main>
        <ArchitectureDiagram />
        <ProblemStatement />
        <Reveal>
          <FeatureHighlights />
        </Reveal>
        <Reveal>
          <ScreenshotStrip />
        </Reveal>
        <TrustBand />
        <EnterpriseCTA />
      </main>
    </Layout>
  );
}
