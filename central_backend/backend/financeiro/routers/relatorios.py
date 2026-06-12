from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
import io
import pandas as pd
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph
from reportlab.lib.styles import getSampleStyleSheet

from backend.core import models
from backend.core.database import get_db
from backend.core.security import get_current_user, require_perfil

router = APIRouter(prefix="/relatorios", tags=["Relatórios e Exportação"], dependencies=[Depends(require_perfil("dashboard"))])


# ==========================================
# EXPORTAÇÃO PARA EXCEL (.XLSX)
# ==========================================
@router.get("/excel/contas")
def exportar_excel_contas(db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    # Puxa apenas as contas do utilizador logado
    contas = db.query(models.Conta).filter(models.Conta.user_id == current_user.id).all()

    dados = []
    for c in contas:
        dados.append({
            "ID": c.id,
            "Descrição": c.descricao,
            "Vencimento": c.vencimento.strftime("%d/%m/%Y"),
            "Tipo": c.tipo_despesa or "",
            "Valor (R$)": c.valor,
            "Natureza": c.natureza or "",  # Removido o .value pois no Postgres gravámos como String pura
            "Status": c.status or ""
        })

    df = pd.DataFrame(dados)
    output = io.BytesIO()

    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Minhas Contas')

    output.seek(0)
    return StreamingResponse(
        output,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=relatorio_contas.xlsx"}
    )


# ==========================================
# EXPORTAÇÃO PARA PDF
# ==========================================
@router.get("/pdf/contas")
def exportar_pdf_contas(db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    contas = db.query(models.Conta).filter(models.Conta.user_id == current_user.id).all()

    output = io.BytesIO()
    doc = SimpleDocTemplate(output, pagesize=letter)
    elementos = []

    estilos = getSampleStyleSheet()
    elementos.append(Paragraph(f"Relatório de Contas - {current_user.email}", estilos['Title']))

    dados_tabela = [["ID", "Descrição", "Vencimento", "Valor", "Status"]]

    for c in contas:
        dados_tabela.append([
            str(c.id),
            c.descricao,
            c.vencimento.strftime("%d/%m/%Y"),
            f"R$ {c.valor:.2f}",
            c.status or ""
        ])

    tabela = Table(dados_tabela)
    tabela.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#4F46E5")),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
        ('GRID', (0, 0), (-1, -1), 1, colors.black)
    ]))

    elementos.append(tabela)
    doc.build(elementos)

    output.seek(0)
    return StreamingResponse(
        output,
        media_type="application/pdf",
        headers={"Content-Disposition": "attachment; filename=relatorio_contas.pdf"}
    )