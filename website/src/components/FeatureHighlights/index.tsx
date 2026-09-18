import type {ReactNode} from 'react';
import Link from '@docusaurus/Link';
import Heading from '@theme/Heading';
import styles from './styles.module.css';

type FeatureItem = {
  title: string;
  description: ReactNode;
  to: string;
};

const FeatureList: FeatureItem[] = [
  {
    title: 'Pick it up where it lives',
    description:
      'vSphere over HTTPS, ESXi over SSH, Azure, or a disk file you already have.',
    to: '/docs/how-it-works',
  },
  {
    title: 'GuestKit, before power-on',
    description:
      'Bootloader, VirtIO, and Windows are repaired on the disk while it is still offline.',
    to: '/docs/how-it-works',
  },
  {
    title: 'One convert command',
    description:
      'A VMDK, VHDX, or raw file you already have becomes qcow2, then the same repair step runs.',
    to: '/docs/getting-started/quickstart',
  },
  {
    title: 'Land it where you run VMs',
    description:
      'KubeVirt clusters (Zorvia, Zeus OS), libvirt hosts (Machina), or OpenStack. One target per run.',
    to: '/docs/how-it-works',
  },
  {
    title: 'Web and CLI',
    description:
      'h2kvmctl for the pipeline. h2kweb for jobs, providers, and status on a real deployment.',
    to: '/gallery',
  },
  {
    title: 'Community, then Enterprise',
    description:
      'Install from PyPI for a lab. Book a demo when the wave needs a named owner.',
    to: '/resources',
  },
];

function Feature({title, description, to}: FeatureItem) {
  return (
    <div className="col col--4">
      <Link to={to} className={styles.card}>
        <Heading as="h3">{title}</Heading>
        <p>{description}</p>
      </Link>
    </div>
  );
}

export default function FeatureHighlights(): ReactNode {
  return (
    <section className={styles.features}>
      <div className="container">
        <div className="row">
          {FeatureList.map((props, idx) => (
            <Feature key={idx} {...props} />
          ))}
        </div>
      </div>
    </section>
  );
}
