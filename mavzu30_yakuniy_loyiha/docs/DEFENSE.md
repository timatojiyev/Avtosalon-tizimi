# Himoya rejasi — “Avtosalon Tizimi”

**Umumiy vaqt:** 15 daqiqa = 10 daqiqa taqdimot + 5 daqiqa jonli demo. Undan keyin savollar.

## 1. Taqdimot (slaydlar bo'yicha)

| # | Slayd | Nima aytiladi | Vaqt |
|---|---|---|---|
| 1 | Sarlavha | Mavzu, ism, guruh | 0:20 |
| 2 | Muammo | Excel, bir avtomobil ikki mijozga, sekin kredit qarori | 0:40 |
| 3 | Maqsad va sifat atributlari | G1–G6; yaxlitlik → mustaqillik → ishonchlilik → kuzatuvchanlik | 0:50 |
| 4 | Kontekst (C4-1) | Kimlar foydalanadi, tashqi tizimlar | 0:30 |
| 5 | Konteynerlar (C4-2) | 12 konteyner, 3 tarmoq, database-per-service | 1:20 |
| 6 | Asosiy qarorlar (ADR) | 10 ta qaror va har birining muqobili | 1:30 |
| 7 | Saga | Ketma-ketlik diagrammasi, kompensatsiya | 1:00 |
| 8 | Hodisalar | Redis Streams, consumer group, at-least-once + idempotentlik | 0:50 |
| 9 | Sifat va testlar | Q1–Q11 ssenariylari, kuzatuv (metrika, iz, chaos), RBAC; 25 ta e2e/integratsiya testi | 0:50 |
| 10 | CI/CD | 7 bosqich, qo'lda tasdiqlash, avtomatik rollback | 0:50 |
| 11 | Xavflar va reja | Texnik qarz va keyingi qadamlar | 0:40 |
| 12 | Xulosa | Natija, demo'ga o'tish | 0:20 |

## 2. Jonli demo ssenariysi (≈ 6 daqiqa)

Tayyorgarlik (himoyadan oldin):
```bash
docker compose up -d --build && scripts/wait-healthy.sh      # → http://localhost:8080
```
Docker bo'lmasa: `./run_local.sh` → http://127.0.0.1:8300. Brauzerda **admin / admin123** bilan kiring.

1. **Kirish va rollar** (30 s). Login sahifasi → `admin`. Yon menyuda 4 bo'lim. Yangi oynada (inkognito) `kredit / kredit123` bilan kiring: “Kuzatuv” va sotuv formasi yo'q, `/ops` ni qo'lda ochsa — **403**. → *Audit jurnalida* bu urinish qizil rangda.
2. **Panel** (20 s). 5 servis yashil, KPI'lar. **“✨ Demo ma'lumot”** → 8 ta sotuv real saga orqali yaratiladi (naqd, kredit, rad etilgan, bekor qilingan).
3. **Hisobotlar** (40 s). Tushum, o'rtacha chek, konversiya, kredit tasdiqlash %, voronka, markalar, holatlar. **CSV** — Excel'da ochiladi.
4. **Kredit kalkulyatori** (40 s). “Sotuvlar” → kredit → mijozni almashtiring: oylik to'lov va **PTI** darhol hisoblanadi, 50 % dan oshsa qizil “rad etilishi kutilmoqda”. Yaratish → natija kalkulyator bilan bir xil.
5. **Saga izi** (40 s). Sotuv sahifasi → o'ng tomonda 5–6 qadam: qaysi servis, natija, ms. “Taqsimlangan iz →”: waterfall — web → sales → customer/car/financing.
6. **Chaos: kompensatsiya** (90 s). “Kuzatuv va chaos” → `financing-service` → **Ishdan chiqarish (503)** → Qo'llash. Kreditli sotuv boshlang → xato: *“…Sotuv bekor qilindi, avtomobil qayta sotuvga chiqarildi (saga kompensatsiyasi)”*. Avtomobil hali ham `sotuvda`. Sotuv sahifasida qizil **xato** qadami va binafsha **KOMPENSATSIYA** qadami. Izda financing 503 qizil. Rejimni **Normal** ga qaytaring.
7. **Hodisalar** (20 s). SMS xabarlari asinxron yetib kelgan.
8. **Masshtablash** (30 s, faqat Docker):
   ```bash
   docker compose up -d --scale car-service=3
   ```
   Panelni yangilaganda car-service kartasidagi so'rovlar soni nusxalar orasida taqsimlanadi.
9. **CI/CD va hujjatlar** (20 s). Barcha servislar bir xil versiyada; “Hujjatlar va ADR” — arc42 va 10 ta ADR.

## 3. Kutilayotgan savollar va javoblar

**S: Nega monolit emas?**
J: Kurs maqsadi va biznes-imkoniyatlar aniq ajralgani uchun. Kredit qoidasi o'zgarsa, faqat financing-service deploy qilinadi. Xarajatini ham tan olaman: saga, tarmoq kechikishi, infratuzilma ko'payadi (ADR-0001). Kichik jamoa uchun modulli monolit ham to'g'ri tanlov bo'lardi.

**S: Ikki menejer bir vaqtda bir avtomobilni sotmoqchi bo'lsa?**
J: `UPDATE cars SET status='band' WHERE id=? AND status='sotuvda'` — atomar amal. Ikkinchi so'rovda `rowcount = 0`, natijada 409 qaytadi. Bu test bilan tekshirilgan.

**S: Sotuv o'rtasida sales-service qulab tushsa?**
J: Bu ma'lum xavf (ARCHITECTURE §11). Hozir kompensatsiya faqat xato *ushlanganda* ishlaydi. Yechim: Transactional Outbox va “N daqiqadan ortiq band, sotuvi yo'q” avtomobillarni davriy tozalovchi vazifa.

**S: Nega Kafka yoki RabbitMQ emas?**
J: Hajm kichik. Redis bitta yengil konteyner, consumer group va pending mexanizmi bor, AOF bilan restartda hodisa yo'qolmaydi. Kafka bu hajm uchun ortiqcha (ADR-0004).

**S: Hodisa ikki marta kelsa?**
J: Kafolat at-least-once. Worker har bir hodisaning `id`'sini saqlaydi va dublikatni tashlab yuboradi (`test_store_is_idempotent`).

**S: Servislar bir-birining bazasiga ulanmasligini nima kafolatlaydi?**
J: Uchta narsa:
- har bir servis faqat o'z `DATABASE_URL`'ini biladi;
- bazalar `data` tarmog'ida joylashgan;
- har bir baza o'z login va paroliga ega.

**S: Nega testlarda SQLite, prod'da PostgreSQL? Farq xavfli emasmi?**
J: Xavf bor, shuning uchun SQL ikkala bazada ishlaydigan qism bilan cheklangan, CI'ning integratsiya bosqichi esa haqiqiy PostgreSQL bilan ishlaydi (ADR-0002).

**S: Deploy muvaffaqiyatsiz bo'lsa nima bo'ladi?**
J: `deploy.sh` health check va read-only smoke test bajaradi. O'tmasa, `.current_tag`'dagi oldingi versiya avtomatik qaytariladi. Qo'lda rollback uchun alohida workflow bor.

**S: Xavfsizlik?**
J:
- konteynerlar non-root, `read_only` va `cap_drop: ALL` bilan ishlaydi;
- bazalar ichki tarmoqda, tashqaridan yopiq;
- gateway'da rate limit, panelda CSRF;
- Trivy CRITICAL zaiflikda deploy'ni to'xtatadi.

Hali yo'q: autentifikatsiya va rollar. Bu keyingi qadam (OIDC/JWT gateway'da).

**S: Qanday masshtablanadi?**
J: Servislar stateless, `--scale` bilan ko'paytiriladi va nginx DNS orqali taqsimlaydi. Worker'lar consumer group orqali hodisalarni bo'lishadi. Bazalar vertikal masshtablanadi; keyingi qadam — read replica.

**S: Eng katta texnik qarz?**
J: Migratsiyalar (`CREATE IF NOT EXISTS` o'rniga versiyalangan migratsiyalar kerak), foydalanuvchilarni konfiguratsiyadan alohida identity-service'ga ko'chirish va metrikalar/izni Prometheus + Jaeger'ga chiqarish.

**S: Autentifikatsiya nega gateway'da emas, web'da?**
J: Foydalanuvchi faqat web (BFF) orqali ishlaydi, servislar ichki tarmoqda yopiq — shuning uchun tekshiruv bitta joyda yetarli va oddiy (ADR-0010). Kamchiligi: servislar ichki chaqiruvchiga ishonadi. Keyingi bosqich — Keycloak (OIDC) va servislarda JWT tekshiruvi.

**S: Parollar qanday saqlanadi? Brute force'ga qarshi nima bor?**
J: Faqat hash (`werkzeug` scrypt). Production'da demo parollar o'chadi, `SECRET_KEY` bo'lmasa web ishga tushmaydi. 5 ta xato urinish → 5 daqiqa blok; login topilmasa ham hash hisoblanadi — javob vaqtidan login mavjudligini bilib bo'lmaydi.

**S: Taqsimlangan iz qanday ishlaydi?**
J: Gateway yoki web har bir so'rovga `X-Request-ID` beradi. `ServiceClient` uni va `X-Caller` ni keyingi servisga avtomatik uzatadi. Har bir servis so'rovni span sifatida xotiraga yozadi (`/traces`), web ularni ID bo'yicha birlashtirib waterfall chizadi. Bu OpenTelemetry tushunchalarining soddalashtirilgan ko'rinishi (ADR-0009).

**S: Chaos rejimi production'da xavfli emasmi?**
J: `APP_ENV=production` bo'lsa endpoint 403 qaytaradi, u gateway orqali tashqariga chiqarilmagan, panelda faqat admin ko'radi va har bir o'zgarish audit jurnaliga yoziladi.

**S: Metrikalar xotirada — 2 ta gunicorn worker bo'lsa nima bo'ladi?**
J: Shuning uchun har bir konteyner 1 jarayon × 8 thread; kengayish konteyner nusxalari orqali (`--scale`). Prometheus har bir nusxani alohida “scrape” qilib yig'adi.

## 4. Baholash mezonlariga muvofiqlik

| Talab | Qayerda |
|---|---|
| Arxitektura uslubi asoslangan | ARCHITECTURE §4, ADR-0001…0010 |
| Diagrammalar (C4, ketma-ketlik) | ARCHITECTURE §3, §5, §6 |
| Ishlaydigan dastur | `docker compose up` / `./run_local.sh` |
| Testlar | `tests/` — unit, integratsiya, e2e, pipeline testlari |
| Konteynerlash va orkestratsiya | Dockerfile ×6, compose (base/override/prod/deploy) |
| CI/CD | `.github/workflows/`, `.gitlab-ci.yml`, `deploy/` |
| Sifat atributlari va xavflar | ARCHITECTURE §10–11 |
| Xavfsizlik | Login, 3 rol (RBAC), audit, CSRF, brute-force himoyasi — ADR-0010 |
| Kuzatuvchanlik | `/metrics` (Prometheus), taqsimlangan iz, saga jurnali, chaos — ADR-0009 |
| Biznes qiymati | Hisobotlar (KPI, voronka, CSV), kredit kalkulyatori |
