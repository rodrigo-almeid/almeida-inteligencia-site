import csv
import io
from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from backend.core.database import get_db
from backend.core.models import Senha, Pessoa
from backend.core.security import get_current_user, require_perfil
from backend.core.models import User

router = APIRouter(dependencies=[Depends(require_perfil("senhas"))])


@router.get("/exportar-csv")
def exportar_csv(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """
    Exporta as senhas do usuário autenticado para CSV de forma segura e leve.
    """
    # 1. Busca as senhas filtrando apenas as que pertencem ao usuário logado via Pessoa
    dados = db.query(Senha).join(Pessoa).filter(Pessoa.user_id == current_user.id).all()

    # 2. Prepara o objeto de escrita em memória (Buffer)
    output = io.StringIO()
    writer = csv.writer(output)

    # 3. Escreve o cabeçalho (senha não é exportada por segurança)
    writer.writerow(["Sistema", "Usuario"])

    # 4. Escreve as linhas de dados sem expor senhas
    for item in dados:
        writer.writerow([item.sistema, item.usuario_sistema])

    # 5. Prepara o stream para envio
    output.seek(0)

    # Converte para bytes e retorna via streaming para performance
    stream = io.BytesIO(output.getvalue().encode('utf-8'))

    return StreamingResponse(
        stream,
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=minhas_senhas.csv"}
    )