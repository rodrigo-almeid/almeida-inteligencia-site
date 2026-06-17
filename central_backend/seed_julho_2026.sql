-- Seed: contas de julho/2026 para br6rodrigo@gmail.com
-- Parceladas: Solar 24/36 (13 parcelas restantes) e Servopa 51/78 (28 parcelas restantes)

DO $$
DECLARE
  uid INTEGER;
  i   INTEGER;
BEGIN
  SELECT id INTO uid FROM users WHERE email = 'br6rodrigo@gmail.com';

  IF uid IS NULL THEN
    RAISE EXCEPTION 'Usuário br6rodrigo@gmail.com não encontrado';
  END IF;

  -- ================================================================
  -- CONTAS ÚNICAS — competência 2026-07
  -- ================================================================
  INSERT INTO contas (descricao, vencimento, competencia, valor, natureza, status, tipo_recorrencia, tipo_despesa, parcela_atual, total_parcelas, mes_seguinte_processado, user_id) VALUES
    ('Salario GH',          '2026-06-30', '2026-07', 6378.92, 'receita',  'pendente', 'unica', NULL,   NULL, NULL, 0, uid),
    ('Copel',               '2026-07-01', '2026-07', 92.88,   'despesa',  'pendente', 'unica', 'fixo', NULL, NULL, 0, uid),
    ('Financiamento Carro', '2026-07-02', '2026-07', 1528.00, 'despesa',  'pendente', 'unica', 'fixo', NULL, NULL, 0, uid),
    ('Salario GW',          '2026-07-07', '2026-07', 5578.42, 'receita',  'pendente', 'unica', NULL,   NULL, NULL, 0, uid),
    ('TIM',                 '2026-07-07', '2026-07', 52.99,   'despesa',  'pendente', 'unica', 'fixo', NULL, NULL, 0, uid),
    ('Unimed',              '2026-07-08', '2026-07', 404.68,  'despesa',  'pendente', 'unica', 'fixo', NULL, NULL, 0, uid),
    ('Sanepar',             '2026-07-08', '2026-07', 262.04,  'despesa',  'pendente', 'unica', 'fixo', NULL, NULL, 0, uid),
    ('Cartão 5265',         '2026-07-09', '2026-07', 1500.00, 'despesa',  'pendente', 'unica', 'fixo', NULL, NULL, 0, uid),
    ('Fundo de Reserva',    '2026-07-10', '2026-07', 0.00,    'despesa',  'pendente', 'unica', 'fixo', NULL, NULL, 0, uid),
    ('Curso Beatriz',       '2026-07-10', '2026-07', 150.00,  'despesa',  'pendente', 'unica', 'fixo', NULL, NULL, 0, uid),
    ('Cartão 0063',         '2026-07-10', '2026-07', 5000.00, 'despesa',  'pendente', 'unica', 'fixo', NULL, NULL, 0, uid),
    ('Chacara Tiago',       '2026-07-10', '2026-07', 436.00,  'receita',  'pendente', 'unica', NULL,   NULL, NULL, 0, uid),
    ('Auxilio Casa Tiago',  '2026-07-10', '2026-07', 500.00,  'despesa',  'pendente', 'unica', 'fixo', NULL, NULL, 0, uid),
    ('Academia Beatriz',    '2026-07-01', '2026-07', 130.00,  'despesa',  'pendente', 'unica', 'fixo', NULL, NULL, 0, uid),
    ('Financiamento Casa',  '2026-07-10', '2026-07', 489.43,  'despesa',  'pendente', 'unica', 'fixo', NULL, NULL, 0, uid),
    ('Cartao Amazon',       '2026-07-10', '2026-07', 1500.00, 'despesa',  'pendente', 'unica', 'fixo', NULL, NULL, 0, uid),
    ('Internet',            '2026-07-10', '2026-07', 149.90,  'despesa',  'pendente', 'unica', 'fixo', NULL, NULL, 0, uid),
    ('Claro Box',           '2026-07-12', '2026-07', 152.55,  'despesa',  'pendente', 'unica', 'fixo', NULL, NULL, 0, uid),
    ('Aluguel Casa',        '2026-07-15', '2026-07', 590.00,  'receita',  'pendente', 'unica', NULL,   NULL, NULL, 0, uid),
    ('Contador',            '2026-07-15', '2026-07', 158.65,  'despesa',  'pendente', 'unica', 'fixo', NULL, NULL, 0, uid),
    ('Dentista',            '2026-07-20', '2026-07', 235.00,  'despesa',  'pendente', 'unica', 'variavel', NULL, NULL, 0, uid),
    ('Boleto Chacara',      '2026-07-20', '2026-07', 872.00,  'despesa',  'pendente', 'unica', 'fixo', NULL, NULL, 0, uid);

  -- ================================================================
  -- SOLAR 24/36 — parcelas 24 a 36 (13 meses)
  -- vencimento base: 30/06/2026, competência base: 2026-07
  -- ================================================================
  FOR i IN 0..12 LOOP
    INSERT INTO contas (descricao, vencimento, competencia, valor, natureza, status, tipo_recorrencia, tipo_despesa, parcela_atual, total_parcelas, mes_seguinte_processado, user_id)
    VALUES (
      'Solar',
      (DATE '2026-06-30' + (i || ' months')::interval)::date,
      TO_CHAR(DATE '2026-07-01' + (i || ' months')::interval, 'YYYY-MM'),
      556.78,
      'despesa',
      'pendente',
      'parcelada',
      'fixo',
      24 + i,
      36,
      0,
      uid
    );
  END LOOP;

  -- ================================================================
  -- SERVOPA 51/78 — parcelas 51 a 78 (28 meses)
  -- vencimento base: 16/07/2026, competência base: 2026-07
  -- ================================================================
  FOR i IN 0..27 LOOP
    INSERT INTO contas (descricao, vencimento, competencia, valor, natureza, status, tipo_recorrencia, tipo_despesa, parcela_atual, total_parcelas, mes_seguinte_processado, user_id)
    VALUES (
      'Servopa',
      (DATE '2026-07-16' + (i || ' months')::interval)::date,
      TO_CHAR(DATE '2026-07-01' + (i || ' months')::interval, 'YYYY-MM'),
      1140.47,
      'despesa',
      'pendente',
      'parcelada',
      'fixo',
      51 + i,
      78,
      0,
      uid
    );
  END LOOP;

  RAISE NOTICE 'Seed concluído para uid=%', uid;
END $$;
