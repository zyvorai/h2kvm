# h2kvm docs site

Built with [Docusaurus](https://docusaurus.io/). Same shape as the Netra docs site. Serves the live docs at https://zyvorai.github.io/h2kvm/.

Curated pages live in `website/docs/`. The repo's longer `docs/` tree stays in GitHub. Screenshots and share cards are not copied into `website/static/` — `staticDirectories` serves `docs/client-presentations/screenshots` and `docs/social` in place.

## Local development

```bash
npm install
npm start
```

## Build

```bash
npm run build
npm run serve
```

## Deployment

`.github/workflows/pages.yml` builds and publishes this site to GitHub Pages on every push to `main` that touches `website/`, the screenshots, or the share cards. Pages must be enabled once, with Source set to GitHub Actions:

```bash
gh api repos/zyvorai/h2kvm/pages -X POST -f build_type=workflow
```
