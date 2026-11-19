.PHONY: install test test-sale unit integration cov html run
install:      ; pip install -r requirements-test.txt
test:         ; pytest
test-sale:    ; pytest tests/unit/test_domain/test_sale.py -v
unit:         ; pytest -m unit
integration:  ; pytest -m integration
cov:          ; pytest --cov=app --cov-config=.coveragerc --cov-report=term-missing
html:         ; pytest --cov=app --cov-config=.coveragerc --cov-report=html && echo "reports/htmlcov/index.html"
run:          ; python run.py
