# ADR-0008: GitHub Actions bilan CI/CD, GHCR, Trivy va avtomatik rollback

**Holat:** Qabul qilingan

## Kontekst
Qo'lda deploy xatolarga olib keladi. Har bir o'zgarish tekshirilishi va production'ga faqat tasdiqlangan versiya chiqishi kerak.

## Qaror
- **CI** (`ci.yml`): ruff, hadolint va compose tekshiruvi → pytest (Python 3.11 va 3.12, coverage ≥ 75 %) → `docker compose up` va smoke test.
- **CD** (`cd.yml`):
  - 6 ta image GHCR'ga push qilinadi; versiya, commit va build vaqti image ichiga yoziladi;
  - Trivy skaneri CRITICAL/HIGH zaiflik topsa, pipeline to'xtaydi;
  - `main` branch → staging;
  - `v*` teg → production (GitHub Environment orqali qo'lda tasdiqlash).
- **Deploy** (`deploy.sh`): pull → up → health check va read-only smoke test. Muvaffaqiyatsiz bo'lsa — **avtomatik rollback** `.current_tag`'ga. Qo'lda rollback uchun alohida workflow bor.
- GitLab CI muqobili ham saqlangan (`.gitlab-ci.yml`).

## Muqobillar
- **Jenkins**: o'z serverini talab qiladi, saqlash xarajati bor.
- **Argo CD (GitOps)**: Kubernetes talab qiladi (ADR-0007 ga zid).

## Oqibatlar
- ✅ Takrorlanadigan reliz, audit izi (Actions loglari, `deploy-history.log`), tez rollback.
- ❌ SSH kaliti va registry tokeni secrets sifatida boshqarilishi kerak. Ma'lumotlar bazasi migratsiyalari hozircha deploy bilan bog'lanmagan (texnik qarz).
