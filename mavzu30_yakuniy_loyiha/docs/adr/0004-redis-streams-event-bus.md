# ADR-0004: Asinxron hodisalar uchun Redis Streams

**Holat:** Qabul qilingan

## Kontekst
Mijozga SMS yuborish va statistika yig'ish sotuv javobini kechiktirmasligi kerak. Hodisalar worker o'chiq paytda ham yo'qolmasligi kerak.

## Qaror
- `sales-service` hodisalarni `XADD avtosalon.events` orqali yozadi.
- `notification-worker` ularni `XREADGROUP` (consumer group) orqali o'qiydi va `XACK` qiladi.
- Ishga tushganda worker avval o'zining *pending* xabarlarini qayta o'qiydi.
- Yetkazish kafolati: at-least-once. Dublikatlar hodisa ID'si bo'yicha tashlab yuboriladi.
- Redis AOF rejimida ishlaydi, shuning uchun restartda hodisalar saqlanadi.
- Lokal rejimda `HttpEventBus` ishlatiladi (Redis'siz).

## Muqobillar
- **RabbitMQ**: routing imkoniyatlari boy, lekin alohida, og'irroq broker va AMQP kutubxonasi kerak.
- **Kafka**: katta oqimlar uchun ideal, ammo bu hajm uchun juda og'ir.
- **Celery**: vazifalar navbati uchun yaxshi, lekin “hodisa” semantikasi va bir nechta obunachi uchun mos emas.

## Oqibatlar
- ✅ Yengil (bitta konteyner), consumer group bilan gorizontal masshtablash (`--scale notification-worker=2`).
- ❌ Kafolat at-least-once bo'lgani uchun handler idempotent bo'lishi shart. Stream uzunligi `MAXLEN ~10000` bilan cheklangan.
