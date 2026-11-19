# O'zgarishlar tarixi
Format: [Keep a Changelog](https://keepachangelog.com/), versiyalash: [SemVer](https://semver.org/).

## [2.0.0] — 2026-11-19
### Qo'shildi
- **Kirish va rollar (RBAC):** login sahifasi, 3 rol (admin, sotuv menejeri, kredit mutaxassisi), har bir route uchun ruxsat, rolga qarab menyu/formalar
- **Xavfsizlik:** parol hash, brute-force blok (5 xato → 5 daqiqa), session fixation va open redirect himoyasi, xavfsizlik header'lari, CSV-injection himoyasi; gateway `/api/*` — `X-API-Key` bilan
- **Audit jurnali:** kirish/chiqish, barcha o'zgartirishlar, rad etilgan ruxsatlar (ixtiyoriy JSONL fayl)
- **Hisobotlar:** tushum, o'rtacha chek, konversiya, kredit tasdiqlash %, o'rtacha PTI, kunlik tushum, markalar, voronka, holatlar (server tomonda SVG); CSV eksport
- **Kuzatuv:** har bir servisda `/metrics` (Prometheus), `/metrics.json`, `/traces`; `X-Request-ID`/`X-Caller` avtomatik uzatiladi; panelda taqsimlangan iz (waterfall)
- **Saga jurnali:** `saga_steps` jadvali, sotuv sahifasida qadamlar (natija, servis, ms), KOMPENSATSIYA qadami
- **Chaos sinovi:** `/admin/chaos` (503 yoki kechikish), panel orqali boshqarish; production'da o'chiq
- **Kredit kalkulyatori:** sotuv formasida oylik to'lov va PTI darhol hisoblanadi
- **Demo-ssenariy:** bir tugma bilan 8 ta real saga (naqd, kredit, rad, bekor)
- Yangi dizayn: yon menyu, KPI kartalari; ADR-0009, ADR-0010; 10 ta yangi test

### O'zgardi
- Gunicorn: 1 jarayon × 8 thread (kengayish — konteyner nusxalari orqali)
- Bog'liq servis 5xx xatosi foydalanuvchiga aniq sabab bilan ko'rsatiladi
- Lokal rejim portlari: panel 8300, servislar 8301–8305

## [1.0.0] — 2026-11-19
### Qo'shildi
- 6 ta image uchun CI/CD pipeline (GitHub Actions + GitLab CI muqobili)
- Lint (ruff, hadolint), Python 3.11/3.12 matritsasida testlar va coverage, integratsiya smoke testi
- GHCR'ga build & push (versiya, commit va build vaqti image'ga yoziladi), Trivy xavfsizlik skaneri
- Staging (main) va production (v* teg, qo'lda tasdiqlash) muhitlariga SSH orqali deploy
- Health check va avtomatik rollback (`deploy/deploy.sh`), qo'lda rollback workflow
- Web panelda “Reliz” sahifasi: har bir servisning versiyasi va commit'i
