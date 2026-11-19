# Mavzu №30 — Yakuniy loyiha: “Avtosalon Tizimi” arxitekturasi va himoyasi

Bu yakuniy loyiha 26–29-ishlarda qurilgan tizimni bitta to'liq dasturiy tizimga birlashtiradi. Unga arxitektura hujjatlari va himoya materiallari qo'shilgan:
- mikroservislar;
- Docker Compose;
- hodisalar (Redis Streams);
- CI/CD.

**v2.0 — “a'lo” darajadagi qo'shimchalar:** login va 3 rol (RBAC), audit jurnali, savdo hisobotlari va CSV,
kredit kalkulyatori, metrikalar (Prometheus), taqsimlangan iz (waterfall), saga jurnali, chaos sinovi,
bir tugmali demo-ssenariy, gateway API kaliti.

## Kirish (demo foydalanuvchilar)
| Login | Parol | Rol | Nima qila oladi |
|---|---|---|---|
| `admin` | `admin123` | Administrator | hammasi: kuzatuv, chaos, audit, CI/CD, demo |
| `menejer` | `menejer123` | Sotuv menejeri | avtomobil, mijoz, sotuv; hisobotlar |
| `kredit` | `kredit123` | Kredit mutaxassisi | kreditlar va sotuvlarni ko'rish; hisobotlar |

Production'da (`APP_ENV=production`) demo parollar o'chadi: `WEB_ADMIN_PASSWORD`, `SECRET_KEY`, `GATEWAY_API_KEY` majburiy.

## Himoya uchun materiallar
| Material | Fayl |
|---|---|
| Arxitektura hujjati (arc42, C4 diagrammalari, ketma-ketlik diagrammalari, sifat ssenariylari, xavflar) | [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) |
| 10 ta arxitektura qarori (ADR): kontekst → qaror → muqobillar → oqibatlar | [`docs/adr/`](docs/adr/) |
| Himoya rejasi, demo ssenariysi, kutilayotgan savollar va javoblar | [`docs/DEFENSE.md`](docs/DEFENSE.md) |
| Taqdimot slaydlari | alohida (Slides) |

Hujjatlarni web panelda ham o'qish mumkin: **Hujjatlar** sahifasi (`/docs`). Diagrammalar u yerda internet bo'lsa Mermaid orqali chiziladi.

## Tizim tarkibi
| Konteyner | Vazifasi |
|---|---|
| gateway (nginx) | yagona kirish :8080, `/api/*` marshrutlash (`X-API-Key` bilan), rate limit, `X-Request-ID` |
| web (BFF) | boshqaruv paneli: login/rollar, sotuvlar, kreditlar, hisobotlar, kuzatuv va chaos, audit, hodisalar, CI/CD, hujjatlar |
| car-service · customer-service · sales-service · financing-service | biznes-servislar, har birining o'z PostgreSQL bazasi bor |
| notification-worker | Redis Streams consumer group orqali SMS xabarlarini tayyorlaydi |
| redis, 4 × postgres | infratuzilma |

## Ishga tushirish (Linux)
**Docker bilan** (to'liq tizim):
```bash
cp .env.example .env
docker compose up -d --build && scripts/wait-healthy.sh
scripts/smoke-test.sh               # avtomatik tekshiruv
```
Kirish: **http://localhost:8080** (API: `curl -H "X-API-Key: $GATEWAY_API_KEY" localhost:8080/api/cars`)

**Docker'siz** (tez demo):
```bash
./run_local.sh                      # → http://127.0.0.1:8300
```

**Testlar va CI tekshiruvlari**:
```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
pytest -q tests                     # unit, integratsiya, e2e, pipeline testlari
SKIP_DOCKER=1 scripts/ci-local.sh   # lint + testlar + coverage
```

## Loyiha tuzilishi
```
docs/                    ARCHITECTURE.md, DEFENSE.md, adr/0001…0010
services/                car, customer, sales, financing, notification-worker
web/                     BFF panel: auth.py (RBAC, audit), analytics.py (hisobot, SVG), extra.py (kuzatuv, chaos, demo)
libs/svc_common/         umumiy kod: DB adapter, HTTP klient, event bus, Flask karkasi, observability (metrika, iz, chaos)
gateway/                 nginx.conf (API Gateway) + templates/ (API kaliti)
docker-compose*.yml      base / override (dev) / prod; deploy/docker-compose.deploy.yml
.github/workflows/       ci.yml, cd.yml, rollback.yml   (+ .gitlab-ci.yml)
deploy/                  deploy.sh (auto-rollback), rollback.sh
scripts/                 wait-healthy, smoke-test, ci-local
tests/                   26 ta test: unit, integratsiya, e2e, RBAC, chaos, pipeline
```

## Avvalgi ishlar bilan bog'liqlik
| Ish | Yakuniy loyihadagi o'rni |
|---|---|
| Lab 26 (pytest, Sale aggregate) | sotuv biznes qoidalari (20 % boshlang'ich to'lov, kredit, holatlar oqimi) va testlash yondashuvi |
| Lab 27 (Docker, 4 servis + 4 DB) | servislar va database-per-service |
| Mavzu 28 (ko'p servisli Compose) | gateway, Redis Streams, worker, masshtablash, profillar |
| Mavzu 29 (CI/CD) | pipeline, registry, skaner, deploy va rollback |
