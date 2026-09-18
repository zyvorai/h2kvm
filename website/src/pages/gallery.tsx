import type {ReactNode} from 'react';
import Layout from '@theme/Layout';
import Heading from '@theme/Heading';
import useBaseUrl from '@docusaurus/useBaseUrl';
import styles from './gallery.module.css';

type Shot = {
  src: string;
  caption: string;
};

const TOUR: Shot[] = [
  {src: '/01-login.png', caption: 'Login'},
  {src: '/02-dashboard.png', caption: 'Dashboard'},
  {src: '/03-providers.png', caption: 'Providers'},
  {src: '/04-migrate.png', caption: 'Migrate'},
  {src: '/05-jobs.png', caption: 'Jobs'},
  {src: '/06-settings.png', caption: 'Settings'},
];

function ShotCard({shot}: {shot: Shot}) {
  const src = useBaseUrl(shot.src);
  return (
    <figure className={styles.shot}>
      <img src={src} alt={shot.caption} loading="lazy" />
      <figcaption>{shot.caption}</figcaption>
    </figure>
  );
}

export default function Gallery(): ReactNode {
  const card = useBaseUrl('/h2kvm-flow.svg');
  return (
    <Layout
      title="Gallery"
      description="A walkthrough of the h2kweb dashboard, captured against a live lab deployment.">
      <header className={styles.header}>
        <div className="container">
          <Heading as="h1">Product tour</Heading>
          <p>
            Every screenshot below is captured against a real, running lab
            deployment — not a mockup.
          </p>
        </div>
      </header>
      <main className="container">
        <div className={styles.demo}>
          <img src={card} alt="h2kvm picks up disks from vSphere, ESXi, Azure and local files, repairs them offline with GuestKit, converts to qcow2, then deploys to a KubeVirt cluster (Zorvia, Zeus OS), a libvirt host (Machina) or OpenStack." />
          <p className={styles.caption}>
            GuestKit repairs the disk and h2kvm lands the VM on one target.
            KubeVirt is Zorvia and Zeus OS, libvirt hosts are Machina, and
            OpenStack is Glance and Nova.
          </p>
        </div>
        <div className={styles.grid}>
          {TOUR.map((shot) => (
            <ShotCard key={shot.src} shot={shot} />
          ))}
        </div>
      </main>
    </Layout>
  );
}
