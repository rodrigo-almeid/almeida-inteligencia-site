"""Inicializa o banco do central_backend com usuário admin e perfis padrão."""
import os
import bcrypt
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://central_user:central_pass_2025@central-db:5432/central_db")
engine = create_engine(DATABASE_URL)
Session = sessionmaker(bind=engine)

# Importa models para criar tabelas
from backend.core.models import Base, User, Perfil
Base.metadata.create_all(bind=engine)

db = Session()

# Perfis padrão
perfis = ["dashboard", "senhas", "abastecimento", "games", "credenciais", "financeiro"]
for nome in perfis:
    exists = db.query(Perfil).filter(Perfil.nome == nome).first()
    if not exists:
        db.add(Perfil(nome=nome))
db.commit()

# Usuário admin
admin_email = os.getenv("ADMIN_EMAIL", "almeidainteligencia@gmail.com")
admin_senha = os.getenv("ADMIN_SENHA", "REDACTED")

user = db.query(User).filter(User.email == admin_email).first()
if not user:
    senha_hash = bcrypt.hashpw(admin_senha.encode(), bcrypt.gensalt(12)).decode()
    user = User(email=admin_email, hashed_password=senha_hash)
    db.add(user)
    db.commit()
    db.refresh(user)

# Atribui todos os perfis ao admin
todos_perfis = db.query(Perfil).all()
for p in todos_perfis:
    if p not in user.perfis:
        user.perfis.append(p)
db.commit()

# Migrations manuais — adiciona colunas que podem não existir
migrations = [
    "ALTER TABLE assistente_config ADD COLUMN IF NOT EXISTS nome_assistente VARCHAR",
    "ALTER TABLE assistente_config ADD COLUMN IF NOT EXISTS personalidade VARCHAR",
    "ALTER TABLE assistente_config ADD COLUMN IF NOT EXISTS tom_voz VARCHAR DEFAULT 'casual'",
    "ALTER TABLE assistente_config ADD COLUMN IF NOT EXISTS instrucoes_extras VARCHAR",
]
for sql in migrations:
    try:
        db.execute(text(sql))
    except Exception:
        pass
db.commit()

db.close()
print(f"Banco inicializado. Admin: {admin_email}")
