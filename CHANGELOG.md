## [1.2.16](https://github.com/lukislp/studylife-webhooks/compare/v1.2.15...v1.2.16) (2026-09-17)


### Bug Fixes

* **deps:** bump ruff from 0.16.6 to 0.16.7 ([b826eee](https://github.com/lukislp/studylife-webhooks/commit/b826eee1ea9e70eaf67084d1a4f1852bb18931b5))

## [1.2.15](https://github.com/lukislp/studylife-webhooks/compare/v1.2.14...v1.2.15) (2026-09-17)


### Bug Fixes

* **docker:** bump astral-sh/uv from 0.12.13 to 0.12.15 ([27ecd51](https://github.com/lukislp/studylife-webhooks/commit/27ecd51e0ba63fd08ad496fe5f79f962269bc298))

## [1.2.14](https://github.com/lukislp/studylife-webhooks/compare/v1.2.13...v1.2.14) (2026-09-13)


### Bug Fixes

* **k8s:** seal studylife-webhooks-secrets so it survives a cluster rebuild ([#44](https://github.com/lukislp/studylife-webhooks/issues/44)) ([d9b42c5](https://github.com/lukislp/studylife-webhooks/commit/d9b42c582f618f744710a3a7593fe339267595e8))

## [1.2.13](https://github.com/lukislp/studylife-webhooks/compare/v1.2.12...v1.2.13) (2026-09-13)


### Bug Fixes

* **k8s:** give probes a 5s timeout so load spikes stop killing pods ([#43](https://github.com/lukislp/studylife-webhooks/issues/43)) ([19bf73e](https://github.com/lukislp/studylife-webhooks/commit/19bf73e983282fd0248e545017f02f3c6c74c314))

## [1.2.12](https://github.com/lukislp/studylife-webhooks/compare/v1.2.11...v1.2.12) (2026-09-13)


### Bug Fixes

* **k8s:** close the open egress hole in this namespace ([#42](https://github.com/lukislp/studylife-webhooks/issues/42)) ([89030c9](https://github.com/lukislp/studylife-webhooks/commit/89030c9b9dc2015a2aa6262433cdf949c987e22b))

## [1.2.11](https://github.com/lukislp/studylife-webhooks/compare/v1.2.10...v1.2.11) (2026-09-13)


### Bug Fixes

* **k8s:** read-only root filesystem for studylife-webhooks ([#41](https://github.com/lukislp/studylife-webhooks/issues/41)) ([31a62e3](https://github.com/lukislp/studylife-webhooks/commit/31a62e372f77920f49bacc1519a8544f2690d6ee))

## [1.2.10](https://github.com/lukislp/studylife-webhooks/compare/v1.2.9...v1.2.10) (2026-09-13)


### Bug Fixes

* **k8s:** add explicit egress policy for the delivery pod ([#40](https://github.com/lukislp/studylife-webhooks/issues/40)) ([5eebc8b](https://github.com/lukislp/studylife-webhooks/commit/5eebc8bf653b697cb7b9004989a75482bddb2425))

## [1.2.9](https://github.com/lukislp/studylife-webhooks/compare/v1.2.8...v1.2.9) (2026-09-13)


### Bug Fixes

* **docker:** apply Debian security updates at build time ([#39](https://github.com/lukislp/studylife-webhooks/issues/39)) ([626ec0f](https://github.com/lukislp/studylife-webhooks/commit/626ec0f32f136eb40937e94722609ad5a2b5201f))

## [1.2.8](https://github.com/lukislp/studylife-webhooks/compare/v1.2.7...v1.2.8) (2026-09-13)


### Bug Fixes

* **k8s:** raise the studylife-webhooks namespace from PSS baseline to restricted ([#38](https://github.com/lukislp/studylife-webhooks/issues/38)) ([0de5e8f](https://github.com/lukislp/studylife-webhooks/commit/0de5e8f19888f9a254e87bf233a62648656e7361))

## [1.2.7](https://github.com/lukislp/studylife-webhooks/compare/v1.2.6...v1.2.7) (2026-09-12)


### Bug Fixes

* **ci:** build the image from the tip of main like get-version does ([#31](https://github.com/lukislp/studylife-webhooks/issues/31)) ([ef69bda](https://github.com/lukislp/studylife-webhooks/commit/ef69bda61aea96ba259512c4b0239ea33fe3be6c))

## [1.2.6](https://github.com/lukislp/studylife-webhooks/compare/v1.2.5...v1.2.6) (2026-09-12)


### Bug Fixes

* **ci:** bump the deployment image tag from the pipeline instead of Flux ([#19](https://github.com/lukislp/studylife-webhooks/issues/19)) ([e792b0c](https://github.com/lukislp/studylife-webhooks/commit/e792b0c7cc53b8a0222d459cb3c496cfd848bf16))

## [1.2.5](https://github.com/lukislp/studylife-webhooks/compare/v1.2.4...v1.2.5) (2026-09-11)


### Bug Fixes

* **ci:** read-only GITHUB_TOKEN in the Dependabot auto-merge workflow ([7658c8c](https://github.com/lukislp/studylife-webhooks/commit/7658c8cf39d2d461eaef8183ad508be1172581b0))

## [1.2.4](https://github.com/lukislp/studylife-webhooks/compare/v1.2.3...v1.2.4) (2026-09-11)


### Bug Fixes

* **deps:** bump ruff from 0.16.5 to 0.16.6 ([79d5aed](https://github.com/lukislp/studylife-webhooks/commit/79d5aed7c30942ed6d1c4357a91fc2e9ec33eea3))

## [1.2.3](https://github.com/lukislp/studylife-webhooks/compare/v1.2.2...v1.2.3) (2026-09-11)


### Bug Fixes

* **ci:** push release commits as a deploy key so the default branch can be ruleset-protected ([2525e49](https://github.com/lukislp/studylife-webhooks/commit/2525e49b0d49bfce8dfaae518b90354eae3e692c))

## [1.2.2](https://github.com/lukislp/studylife-webhooks/compare/v1.2.1...v1.2.2) (2026-09-04)


### Bug Fixes

* **ci:** ignore base image major bumps in Dependabot ([b52c22e](https://github.com/lukislp/studylife-webhooks/commit/b52c22e8afac011c4e7b7d8d6bf3a82336653fb8))

## [1.2.1](https://github.com/lukislp/studylife-webhooks/compare/v1.2.0...v1.2.1) (2026-09-04)


### Bug Fixes

* **ci:** bump aquasecurity/trivy-action ([a0bdea3](https://github.com/lukislp/studylife-webhooks/commit/a0bdea369d33c898526c304c90641626c0822819))
* **ci:** bump astral-sh/setup-uv from 9.0.0 to 10.0.1 ([434d6e1](https://github.com/lukislp/studylife-webhooks/commit/434d6e18c9edadb47a1d2d8290db36d00006a662))
* **ci:** bump docker/setup-buildx-action from 4.2.0 to 4.3.0 ([a307ba5](https://github.com/lukislp/studylife-webhooks/commit/a307ba5a446373a19c5b34efa927d0a18d6adf65))

# [1.2.0](https://github.com/lukislp/studylife-webhooks/compare/v1.1.1...v1.2.0) (2026-09-03)


### Features

* expose Prometheus metrics for webhook delivery and HTTP requests ([c317c91](https://github.com/lukislp/studylife-webhooks/commit/c317c91e744248ae2066e28821a5bec4b126957c))

## [1.1.1](https://github.com/lukislp/studylife-webhooks/compare/v1.1.0...v1.1.1) (2026-09-03)


### Bug Fixes

* **ci:** add Dependabot for github-actions, uv, docker ([7f8a3ac](https://github.com/lukislp/studylife-webhooks/commit/7f8a3ac584727a8365e34de27dd87a8902353905))

# [1.1.0](https://github.com/lukislp/studylife-webhooks/compare/v1.0.0...v1.1.0) (2026-08-29)


### Features

* document the expanded webhook event catalog ([39c083a](https://github.com/lukislp/studylife-webhooks/commit/39c083a1b46380591e3f82c46c537c6decdae642))

# 1.0.0 (2026-08-29)


### Features

* add production Docker/release pipeline and Kubernetes manifests ([bb5ca43](https://github.com/lukislp/studylife-webhooks/commit/bb5ca43dd6ad3d7366e6e9bc5de48ddd8460f3b4))
* scaffold the StudyLife Webhooks microservice ([528f44a](https://github.com/lukislp/studylife-webhooks/commit/528f44a1e80173df923dd082b17e1e1971b0acd5))
