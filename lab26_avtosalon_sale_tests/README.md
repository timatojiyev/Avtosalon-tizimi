# Laboratoriya ishi №26 — 15-topshiriq

**Mavzu:** Pytest yordamida arxitektura komponentlarini testlash.

**Topshiriq:** “Avtosalon Tizimi” uchun `tests/unit/test_domain/test_sale.py` faylida Sale aggregate testlarini yozing. Sotuvni boshlash, kredit tasdiqlash, sotuvni yakunlash testlarini yozing.

## Asosiy fayl — `tests/unit/test_domain/test_sale.py` (59 ta test)
| Test klassi | Nimani tekshiradi |
|---|---|
| `TestInitiateSale` | naqd va kredit sotuvni boshlash, avtomobil band qilinishi, sotuvda bo'lmagan avtomobil, mijoz ismi, boshlang'ich to'lov chegaralari (20 %) — `parametrize` |
| `TestFinancingRequest` | kredit so'rash, noto'g'ri muddat/foiz, takroriy so'rov |
| `TestFinancingApproval` | **kredit tasdiqlash**: annuitet oylik to'lov (4 ta holat), bank kamroq summa tasdiqlashi, foiz/muddat o'zgarishi, ortiqcha summa taqiqi, hodisa |
| `TestFinancingRejection` | rad etish, sabab majburiy, naqd to'lovga o'tish |
| `TestCompleteSale` | **sotuvni yakunlash**: naqd/kredit, yetarli bo'lmagan to'lov, qaytim, tasdiqlanmasdan yakunlab bo'lmaydi, ikki marta yakunlab bo'lmaydi |
| `TestCancelSale` | har bir holatdan bekor qilish, avtomobil bo'shatilishi |
| `TestSaleLifecycle` | to'liq jarayon va domen hodisalari ketma-ketligi, yakuniy holatlar |

Qo'shimcha: `test_car.py`, `test_value_objects.py`, `test_application/test_sales_service.py` (mock repository + mock event bus), `integration/test_sales_api.py`. Jami 93 ta test. Domen va application qatlamlari to'liq qamrab olingan.

Testlanadigan kod: `app/domain/sale.py` (Sale aggregate va uning biznes qoidalari).

## Ishga tushirish (Linux)
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-test.txt

pytest tests/unit/test_domain/test_sale.py -v     # faqat topshiriq testlari
pytest                                            # barcha testlar
pytest -m unit                                    # faqat unit testlar
pytest --cov=app --cov-report=term-missing        # coverage (minimum 80 %, .coveragerc)
```
yoki `make test-sale`, `make cov`.

## Web sayt
```bash
./run.sh          # yoki: python run.py
```
**http://127.0.0.1:5026**
- **Avtomobillar va sotuvlar** — sotuvni brauzerda bosqichma-bosqich o'tkazish (boshlash → kredit → tasdiqlash → yakunlash) va domen hodisalarini ko'rish.
- **Testlar** — “▶ test_sale.py” tugmasi pytest'ni ishga tushiradi; natijalar test klasslari bo'yicha, coverage foizi bilan ko'rsatiladi.
