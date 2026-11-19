# ADR-0003: Sotuv uchun orkestratsiyalangan saga

**Holat:** Qabul qilingan

## Kontekst
Sotuvni boshlash 3 ta servisga tegadi: mijozni tekshirish, avtomobilni band qilish va kredit qarori. Bazalar alohida bo'lgani uchun umumiy ACID tranzaksiya yo'q.

## Qaror
`sales-service` orkestrator vazifasini bajaradi va qadamlarni ketma-ket chaqiradi:
1. Mijoz va avtomobilni tekshiradi.
2. `reserve` — avtomobil holati shartli `UPDATE` bilan o'zgaradi, shuning uchun bir vaqtdagi so'rovlarda poyga (race) bo'lmaydi.
3. Sotuv yozuvini yaratadi.
4. Kredit arizasini yuboradi.

Istalgan qadam muvaffaqiyatsiz bo'lsa, **kompensatsiya** bajariladi: avtomobil `release` qilinadi va sotuv `bekor_qilingan` deb belgilanadi.

## Muqobillar
- **Xoreografiya (faqat hodisalar orqali)**: bog'liqlik kamroq, lekin jarayonni kuzatish va tushuntirish qiyin.
- **2PC (ikki fazali commit)**: HTTP servislar uchun amaliy emas, bloklaydi.

## Oqibatlar
- ✅ Jarayon bitta joyda, o'qilishi va testlanishi oson (`test_compensation_when_financing_down`).
- ❌ Orkestrator markaziy nuqtaga aylanadi. Jarayon o'rtasida qulasa, kompensatsiya bajarilmay qolishi mumkin. Keyingi qadam: outbox va “osilib qolgan band”larni davriy tozalash.
