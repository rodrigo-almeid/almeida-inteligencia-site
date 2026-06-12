#!/bin/bash
set -e
echo "=== Instalando dependências de teste ==="
pip install -r requirements-test.txt -q

echo ""
echo "=== Rodando testes do portal backend ==="
pytest tests/ \
  --cov=main \
  --cov-report=term-missing \
  --cov-report=html:htmlcov \
  --cov-fail-under=85 \
  -v

echo "Relatório HTML: htmlcov/index.html"
