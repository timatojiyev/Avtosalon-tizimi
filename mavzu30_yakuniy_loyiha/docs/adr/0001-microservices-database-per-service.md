# ADR-0001: Mikroservislar va database-per-service

**Holat:** Qabul qilingan · **Sana:** 2026-11-01

## Kontekst
Tizimda 4 ta aniq biznes-imkoniyat bor: ombor, mijozlar, sotuv va kredit. Ular turli tezlikda o'zgaradi. Masalan, kredit qoidalari tez-tez o'zgaradi, ombor esa barqaror. Kurs talabi mikroservis arxitekturasini ko'rsatishni so'raydi.

## Qaror
Biznes-imkoniyatlar bo'yicha 4 ta servis ajratiladi: `car`, `customer`, `sales`, `financing`. Xabarnomalar uchun alohida worker bo'ladi.
- Har bir servis **faqat o'z bazasiga** egalik qiladi.
- Boshqa servis ma'lumotiga faqat uning API'si orqali murojaat qilinadi.

## Muqobillar
- **Modulli monolit**: deploy oddiy, tranzaksiyalar oson. Lekin mustaqil deploy va masshtablash yo'q, kurs maqsadiga mos emas.
- **Umumiy baza + bir nechta servis**: jadvallar orqali yashirin bog'liqlik paydo bo'ladi (“distributed monolith”).

## Oqibatlar
- ✅ Mustaqil deploy, masshtablash, texnologiya tanlash erkinligi; xatolar izolyatsiyasi.
- ❌ Taqsimlangan tranzaksiyalar (saga kerak, ADR-0003), tarmoq kechikishi, ko'proq infratuzilma.
- ❌ Hisobotlar uchun ma'lumotlarni birlashtirish qiyinlashadi (keyinchalik: hodisalar asosida analitika).
