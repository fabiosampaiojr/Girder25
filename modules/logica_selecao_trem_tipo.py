# ============================================================================
# Girder25 - logica_selecao_trem_tipo.py
# Autor: Fábio Henrique Sampaio Júnior
# Controlador da janela de seleção do trem-tipo e carga do passeio.
# ============================================================================

import os
from PyQt6.QtWidgets import QDialog, QMessageBox, QVBoxLayout, QLabel
from PyQt6.QtGui import QPixmap
from PyQt6.QtCore import Qt

from ui.janela_selecao_trem_tipo import Ui_janela_selecao_trem_tipo
from modules.gerar_html import obter_html_trem_tipo
from modules.logica_resultado_trem_tipo_longarina import LogicaResultadoTremTipoLongarina
from modules.visualizador_pdf import PDFViewer
from modules.utils import resource_path


class LogicaSelecaoTremTipo(QDialog, Ui_janela_selecao_trem_tipo):
    """
    Diálogo para definição do trem-tipo (TB-450 ou TB-240) e da carga
    de passeio. Exibe a ilustração do veículo e, ao confirmar, abre a
    janela de resultados da distribuição transversal.
    """

    def __init__(self, gerenciador):
        super().__init__()
        self.setupUi(self)
        self.gerenciador = gerenciador

        # -----------------------------------------------------------------
        # Ilustração do trem-tipo
        # -----------------------------------------------------------------
        self.layout_desenho = QVBoxLayout(self.desenho)
        self.layout_desenho.setContentsMargins(0, 0, 0, 0)

        self.lbl_imagem = QLabel()
        self.lbl_imagem.setAlignment(Qt.AlignmentFlag.AlignCenter)
        caminho_img = resource_path("assets/img_trem_tipo.png")

        if os.path.exists(caminho_img):
            pixmap = QPixmap(caminho_img)
            self.lbl_imagem.setPixmap(
                pixmap.scaled(
                    self.desenho.size(),
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation
                )
            )
        else:
            self.lbl_imagem.setText(
                "Imagem do trem-tipo não encontrada em assets/img_trem_tipo.png"
            )
        self.layout_desenho.addWidget(self.lbl_imagem)

        # -----------------------------------------------------------------
        # Combo de seleção do trem-tipo e HTML descritivo
        # -----------------------------------------------------------------
        self.combo_tipo_trem.clear()
        self.combo_tipo_trem.addItems(["TB-450", "TB-240"])
        self.combo_tipo_trem.currentTextChanged.connect(self.atualizar_html_trem_tipo)
        self.atualizar_html_trem_tipo()

        # -----------------------------------------------------------------
        # Carga de passeio
        # -----------------------------------------------------------------
        self.spin_passeio.setRange(1, 7)
        self.spin_passeio.setValue(3)
        self.spin_passeio.setSuffix(" kN/m²")

        # -----------------------------------------------------------------
        # Conexões dos botões
        # -----------------------------------------------------------------
        self.confirmar.clicked.connect(self.confirmar_selecao)
        self.cancelar.clicked.connect(self.reject)
        self.manual.clicked.connect(self.abrir_manual)

    # -------------------------------------------------------------------------
    # Atualização do HTML descritivo
    # -------------------------------------------------------------------------
    def atualizar_html_trem_tipo(self):
        """Atualiza a descrição do trem-tipo conforme a seleção na combo."""
        selecao = self.combo_tipo_trem.currentText()
        tipo_param = "tb_450" if "450" in selecao else "tb_240"
        html_gerado = obter_html_trem_tipo(tipo_param)
        self.html_trem_tipo.setText(html_gerado)

    # -------------------------------------------------------------------------
    # Confirmação e abertura da janela de resultados
    # -------------------------------------------------------------------------
    def confirmar_selecao(self):
        """
        Coleta os parâmetros escolhidos, abre a janela de distribuição
        transversal e, se o usuário confirmar os resultados, aceita este diálogo.
        """
        selecao = self.combo_tipo_trem.currentText()
        if "450" in selecao:
            trem_tipo = (75.0, 5.0)   # (Q, q) para TB-450
        else:
            trem_tipo = (40.0, 4.0)   # (Q, q) para TB-240

        p_linha = float(self.spin_passeio.value())

        dialog_resultado = LogicaResultadoTremTipoLongarina(
            self.gerenciador, trem_tipo, p_linha
        )

        if dialog_resultado.exec():
            self.accept()

    # =========================================================================
    # Manual do usuário
    # =========================================================================
    def abrir_manual(self):
        """
        Abre o manual do software no PDFViewer na seção de seleção do trem-tipo
        e carga do passeio.

        Navega diretamente para a página 47 do manual (índice 46 em base 0,
        pois o PyMuPDF (fitz) indexa páginas a partir de zero).
        """
        pdf_path = resource_path(os.path.join("assets", "Manual Girder25 Dark.pdf"))
        viewer = PDFViewer(pdf_path, "Manual: SELEÇÃO DO TREM-TIPO E CARGA DO PASSEIO")
        viewer.display_page(46)   # página 47 do manual → índice 46
        viewer.exec()