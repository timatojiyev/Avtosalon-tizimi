# ADR-0006: Flask + gunicorn

**Holat:** Qabul qilingan

## Kontekst
Servislar kichik, sinxron va asosan I/O bilan ishlaydi (DB va HTTP). Jamoa Flask'ni yaxshi biladi. Bitta stack'da ham API'lar, ham server tomonda render qilinadigan UI kerak.

## Qaror
- Barcha servislar va web uchun Flask 3 ishlatiladi.
- Production'da `gunicorn` **1 jarayon × 8 thread** bilan ishlaydi (notification-worker: 1 × 4). Gorizontal kengayish jarayonlar emas, konteyner nusxalari (`--scale`) orqali: shunda jarayon ichidagi metrikalar, iz va chaos holati bitta nusxaga tegishli va izchil bo'ladi (ADR-0009).
- Umumiy karkas `create_service_app` (health, ready, xatolar, loglar) — barcha servislar bir xil ko'rinishda.

## Muqobillar
- **FastAPI**: avtomatik OpenAPI va async imkoniyatlari bor. Bu yuklamada afzallik kam, qo'shimcha bog'liqliklar ko'p (5-labda alohida ko'rsatilgan).
- **Django**: to'liq freymvork, mikroservis uchun og'ir.

## Oqibatlar
- ✅ Kam bog'liqlik, tez ishga tushish, test client bilan oson testlash.
- ❌ OpenAPI spetsifikatsiyasi avtomatik emas — README va testlarda hujjatlashtirilgan. Keyingi qadam: `flask-smorest` yoki FastAPI'ga ko'chish.
