# ADR-0009: Kuzatuvchanlik — metrikalar, taqsimlangan iz va chaos sinovi

**Holat:** Qabul qilingan (v2.0.0)

## Kontekst
Bitta sotuv 5 ta servisdan o'tadi (web → sales → customer, car, financing → worker). Loglar `request_id` bilan yozilgan bo'lsa ham, “sotuv nega sekin?” yoki “nega bekor bo'ldi?” degan savolga javob topish uchun 5 ta log oqimini qo'lda solishtirish kerak edi. Bundan tashqari, saga kompensatsiyasi faqat testlarda tekshirilgan, uni ishlab turgan tizimda ko'rsatishning yo'li yo'q edi.

## Qaror
1. **Metrikalar.** `svc_common.observability.Metrics` har bir endpoint uchun so'rovlar, 5xx xatolar va kechikish gistogrammasini yig'adi. `GET /metrics` — Prometheus matn formati (`http_requests_total`, `http_request_duration_ms_bucket`), `GET /metrics.json` — panel uchun (p50/p95).
2. **Taqsimlangan iz.** Har bir so'rov `Span` (request_id, servis, yo'l, status, boshlanish, davomiylik, chaqiruvchi) sifatida xotiradagi halqa buferga (1000 ta) yoziladi. `ServiceClient` Flask kontekstidan `X-Request-ID` va `X-Caller` ni **avtomatik** uzatadi — servis kodida qo'lda uzatish shart emas. Web `GET /traces?request_id=…` ni barcha servislardan parallel yig'ib, waterfall diagramma chizadi.
3. **Saga jurnali.** `sales-service` har bir saga qadamini (`saga_steps` jadvali: qadam, servis, natija, tafsilot, ms) bazaga yozadi — xotiradagi izdan farqli ravishda u restartdan keyin ham saqlanadi.
4. **Chaos.** `POST /admin/chaos {"mode": "error"|"latency"|"off"}` servisni ataylab 503 qaytaradigan yoki sekin ishlaydigan qiladi (`/health`, `/ready`, `/metrics` ishlayveradi — konteyner qayta ishga tushirilmaydi). `APP_ENV=production` yoki `CHAOS_ENABLED=0` bo'lsa o'chiq. Endpoint gateway orqali tashqariga chiqarilmagan.
5. Gunicorn **1 jarayon × N thread** bilan ishlaydi, kengayish — konteyner nusxalari orqali; shunda xotiradagi holat (metrika, chaos) bitta nusxaga izchil tegishli bo'ladi.

## Muqobillar
- **OpenTelemetry + Jaeger + Prometheus + Grafana:** sanoat standarti, lekin 4 ta qo'shimcha konteyner va kutubxonalar talab qiladi; o'quv loyihasi uchun og'ir. Bizning format OTel tushunchalariga (trace/span/parent) mos — keyinchalik ko'chish oson.
- **Faqat loglar (ELK):** qidirish mumkin, lekin vaqt bo'yicha vizualizatsiya va p95 yo'q.

## Oqibatlar
- ✅ Bitta so'rovning servislar bo'ylab yo'li va qaysi servis xato bergani bir qarashda ko'rinadi.
- ✅ Himoyada kompensatsiyani jonli ko'rsatish mumkin (financing → 503 → avtomobil qayta sotuvda).
- ✅ `/metrics` Prometheus'ga ulashga tayyor.
- ❌ Iz va metrikalar xotirada — restartda yo'qoladi; ko'p nusxada har bir nusxa o'z ma'lumotini beradi (Prometheus yig'ishi kerak).
