# O'zgarishlar tarixi
Format: [Keep a Changelog](https://keepachangelog.com/), versiyalash: [SemVer](https://semver.org/).

## [1.0.0] — 2026-11-19
### Qo'shildi
- 6 ta image uchun CI/CD pipeline (GitHub Actions + GitLab CI muqobili)
- Lint (ruff, hadolint), Python 3.11/3.12 matritsasida testlar va coverage, integratsiya smoke testi
- GHCR'ga build & push (versiya, commit va build vaqti image'ga yoziladi), Trivy xavfsizlik skaneri
- Staging (main) va production (v* teg, qo'lda tasdiqlash) muhitlariga SSH orqali deploy
- Health check va avtomatik rollback (`deploy/deploy.sh`), qo'lda rollback workflow
- Web panelda “Reliz” sahifasi: har bir servisning versiyasi va commit'i
