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
  const card = useBaseUrl('/h2kvm-suite-card.png');
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
          <img src={card} alt="GuestKit, h2kvm, Zorvia, Zeus OS, and Machina" />
          <p className={styles.caption}>
            GuestKit inspects the disk. h2kvm lands the VM. Zorvia is where
            you watch the boot. Zeus OS and Machina are where you keep
            running it.
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
