# ============================================================================
# Girder25 - logica_janela_memorial.py
# Autor: Fábio Henrique Sampaio Júnior
# Janela genérica para exibição de memoriais de cálculo em HTML.
# ============================================================================

import os
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QTextEdit, QPushButton, QHBoxLayout,
    QFileDialog, QMessageBox
)
from PyQt6.QtGui import QTextDocument
from PyQt6.QtPrintSupport import QPrinter
from ui.janela_memorial import Ui_janela_memorial
from modules.visualizador_pdf import PDFViewer
from modules.utils import resource_path


class LogicaJanelaMemorial(QDialog, Ui_janela_memorial):
    """
    Janela reutilizável para visualização de memoriais de cálculo formatados em HTML.
    O conteúdo é apenas leitura e pode ser exportado como arquivo HTML ou PDF.
    """

    def __init__(self, titulo: str, html_content: str, parent=None):
        super().__init__(parent)
        self.setupUi(self)

        self.setWindowTitle(titulo)
        self.resize(1000, 670)
        self.html_content = html_content

        # Exibe o HTML no campo de texto definido na UI
        self.textEdit_memorial.setHtml(self.html_content)
        self.textEdit_memorial.setReadOnly(True)

        # Conexões dos botões
        self.exportar.clicked.connect(self.exportar_memorial)
        self.ok.clicked.connect(self.accept)
        self.manual.clicked.connect(self.abrir_manual)

    def exportar_memorial(self):
        """
        Abre diálogo para salvar o memorial em arquivo HTML ou PDF.
        O formato é determinado pela extensão escolhida pelo usuário.
        """
        filtros = "Documento HTML (*.html);;Documento PDF (*.pdf)"
        caminho, tipo_filtro = QFileDialog.getSaveFileName(
            self,
            "Exportar Memorial de Cálculo",
            "",
            filtros
        )

        if not caminho:
            return

        try:
            # Exportação como HTML
            if "html" in tipo_filtro.lower() or caminho.lower().endswith(".html"):
                if not caminho.lower().endswith(".html"):
                    caminho += ".html"
                with open(caminho, 'w', encoding='utf-8') as f:
                    f.write(self.html_content)

            # Exportação como PDF utilizando QPrinter
            elif "pdf" in tipo_filtro.lower() or caminho.lower().endswith(".pdf"):
                if not caminho.lower().endswith(".pdf"):
                    caminho += ".pdf"

                printer = QPrinter(QPrinter.PrinterMode.HighResolution)
                printer.setOutputFormat(QPrinter.OutputFormat.PdfFormat)
                printer.setOutputFileName(caminho)

                doc = QTextDocument()
                doc.setHtml(self.html_content)
                doc.print(printer)

            QMessageBox.information(self, "Sucesso", "Memorial exportado com sucesso!")

        except Exception as e:
            QMessageBox.critical(
                self,
                "Erro na Exportação",
                f"Não foi possível salvar o arquivo.\nDetalhe: {str(e)}"
            )

    def abrir_manual(self):
        """
        Abre o manual do software no PDFViewer na seção do memorial de cálculo.

        Navega diretamente para a página 87 do manual (índice 86 em base 0,
        pois o PyMuPDF (fitz) indexa páginas a partir de zero).
        """
        pdf_path = resource_path(os.path.join("assets", "Manual Girder25 Dark.pdf"))
        viewer = PDFViewer(pdf_path, "Manual: MEMORIAL DE CÁLCULO")
        viewer.display_page(86)   # página 87 do manual → índice 86
        viewer.exec()