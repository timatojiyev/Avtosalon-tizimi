# Mavzu №29 — Python loyihasi uchun CI/CD pipeline va deployment

Asos: 28-mavzudagi “Avtosalon Tizimi”. Unda 6 ta image bor (4 ta servis, notification-worker, web), shuningdek gateway, Redis va 4 ta PostgreSQL.

## Pipeline
```
push / PR ─► CI:  lint ─► test (Py 3.11, 3.12) ─► integratsiya (compose up + smoke)
                                                        │ muvaffaqiyatli bo'lsa
main / v* ─► CD:  prepare ─► build & push ×6 (GHCR) ─► Trivy skaner ─► deploy
                                                          main → staging   (avtomatik)
                                                          v1.2.3 → production (qo'lda tasdiqlash)
```

| Fayl | Vazifasi |
|---|---|
| `.github/workflows/ci.yml` | ruff, hadolint, compose tekshiruvi → pytest matritsasi (JUnit + coverage, ≥ 75 %) → `docker compose up` + smoke test |
| `.github/workflows/cd.yml` | versiyani aniqlash (`sha-xxxxxxx` yoki `1.2.3`), 6 ta image'ni GHCR'ga push (kesh, SBOM), Trivy (CRITICAL/HIGH → to'xtatish), SSH orqali deploy |
| `.github/workflows/rollback.yml` | qo'lda rollback (muhit + versiya) |
| `.gitlab-ci.yml` | GitLab CI muqobili (xuddi shu bosqichlar) |
| `deploy/deploy.sh` | serverda: pull → up → health + read-only smoke → muvaffaqiyatsiz bo'lsa **avtomatik rollback**; `deploy-history.log` |
| `deploy/rollback.sh` | oldingi (`.previous_tag`) yoki ko'rsatilgan versiyaga qaytish |
| `deploy/docker-compose.deploy.yml` | serverda image'lar registry'dan olinadi (`pull_policy: always`) |
| `pyproject.toml`, `.pre-commit-config.yaml` | ruff, pytest, coverage sozlamalari; commit'dan oldingi tekshiruvlar |
| `scripts/ci-local.sh` | CI'ni lokal kompyuterda ishga tushirish |
| `tests/test_cicd.py` | “pipeline as code” testlari (bosqichlar tartibi, barcha image'lar build qilinishi, skanersiz deploy yo'qligi, Dockerfile xavfsizligi) |

Har bir image'ga versiya, commit SHA va build vaqti yoziladi. Ular `/health` orqali qaytadi va panelning **CI/CD** sahifasida ko'rinadi.

## Sozlash (bir martalik)
1. Loyihani GitHub'ga push qiling.
2. **Settings → Environments** bo'limida `staging` va `production` muhitlarini yarating. `production` uchun **Required reviewers** qo'shing.
3. Har bir muhitga quyidagilarni kiriting:
   - Secrets: `DEPLOY_HOST`, `DEPLOY_USER`, `DEPLOY_SSH_KEY`
   - Variables: `DEPLOY_PATH` (masalan `/opt/avtosalon`), `PUBLIC_URL`
4. Serverda:
   - Docker o'rnating;
   - `mkdir -p /opt/avtosalon`;
   - `.env.example` asosida `/opt/avtosalon/.env` faylini yarating (DB parollari).

Shundan keyin:
- `main` branch'ga push → staging'ga avtomatik deploy;
- `git tag v1.0.0 && git push origin v1.0.0` → production'ga (tasdiqlashdan keyin) deploy.

## Lokal ishlatish (Linux)
```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
pre-commit install                 # ixtiyoriy
make ci                            # = scripts/ci-local.sh (lint + test + docker integratsiya)
SKIP_DOCKER=1 make ci              # Docker'siz: faqat lint + test
make up                            # tizimni ko'tarish → http://localhost:8080  (CI/CD sahifasi: /release)
./run_local.sh                     # Docker'siz demo → http://127.0.0.1:8290
```
