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
    title: 'Any hypervisor, one pipeline',
    description:
      'Export and convert from VMware, Hyper-V, Nutanix, AWS, Azure, and GCP to qcow2/raw — browse, migrate, deploy as one pipeline instead of an 18-month migration project.',
    to: '/docs/README',
  },
  {
    title: 'GuestKit offline fix',
    description:
      'Guest drivers that break on first KVM boot get fixed offline via GuestKit — VirtIO, GRUB, hivex/registry for Windows — across 35+ guest OS versions.',
    to: '/docs/architecture/GUESTKIT',
  },
  {
    title: 'h2kweb control plane',
    description:
      'A real web dashboard for migration progress, providers, and jobs — plus webhooks and email, so conversion isn\'t a black box.',
    to: '/docs/README',
  },
  {
    title: 'Kubernetes-native operator',
    description:
      'A K8s/OLM operator and Helm charts take libvirt → KubeVirt from YAML tribal knowledge to a one-click, declarative path.',
    to: '/docs/operator/getting-started',
  },
  {
    title: 'CLI and web',
    description:
      'h2kvmctl / h2k for scripting, h2kweb for the dashboard — pick the surface that fits the job.',
    to: '/docs/deployment/deploy-remote',
  },
  {
    title: 'Community vs Enterprise',
    description:
      'CE proves convert for labs and single-cluster PoC. Enterprise adds HA, multi-wave cutover fabric, SAN/Ceph storage pipelines, and an SLA/LTS/CVE support contract.',
    to: '/docs/ce-vs-enterprise',
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
