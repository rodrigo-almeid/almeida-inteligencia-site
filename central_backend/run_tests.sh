#!/bin/bash
# Executa todos os testes do central_backend com relatório de cobertura
set -e

echo "=== Instalando dependências de teste ==="
pip install -r requirements-test.txt -q

echo ""
echo "=== Rodando testes ==="
pytest tests/ \
  --cov=backend \
  --cov-report=term-missing \
  --cov-report=html:htmlcov \
  --cov-fail-under=85 \
  -v

echo ""
echo "Relatório HTML gerado em: htmlcov/index.html"
