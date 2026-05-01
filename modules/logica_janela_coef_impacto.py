# ============================================================================
# Girder25 - logica_janela_coef_impacto.py
# Autor: Fábio Henrique Sampaio Júnior
# Controlador da janela de visualização dos coeficientes de impacto.
# ============================================================================

import os
from PyQt6.QtWidgets import (
    QDialog, QMessageBox, QVBoxLayout, QLabel,
    QFileDialog, QTableWidget, QTableWidgetItem,
    QHeaderView, QComboBox, QPushButton, QHBoxLayout
)
from PyQt6.QtCore import Qt
import matplotlib.pyplot as plt
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas

from ui.janela_coef_impacto import Ui_janela_coef_impacto
from modules.Calculadora_Coeficiente_Impacto import CalculadoraCoeficienteImpacto
from modules.desenho_dcl_coef import desenhar_figura_coeficiente
from modules.gerar_html import gerar_html_memorial_coef
from modules.logica_janela_def_superestrutura import DialogoExportacao
from modules.exportar_dxf import exportar_figura_para_dxf
from modules.exportador import exportar_tabela
from modules.logica_janela_memorial import LogicaJanelaMemorial
from modules.visualizador_pdf import PDFViewer
from modules.utils import resource_path


class DialogoExportacaoTabela(QDialog):
    """Diálogo para escolha do formato de exportação da tabela (XLS, PDF, TXT)."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Exportar Tabela")
        self.setFixedSize(250, 120)
        self.formato_escolhido = "xls"

        layout = QVBoxLayout(self)

        lbl = QLabel("Selecione o formato de exportação:")
        layout.addWidget(lbl)

        self.combo_formato = QComboBox()
        self.combo_formato.addItems(["xls", "pdf", "txt"])
        layout.addWidget(self.combo_formato)

        btn_layout = QHBoxLayout()
        btn_ok = QPushButton("Confirmar")
        btn_cancel = QPushButton("Cancelar")

        btn_ok.clicked.connect(self.aceitar)
        btn_cancel.clicked.connect(self.reject)

        btn_layout.addWidget(btn_ok)
        btn_layout.addWidget(btn_cancel)
        layout.addLayout(btn_layout)

    def aceitar(self):
        self.formato_escolhido = self.combo_formato.currentText()
        self.accept()


class LogicaJanelaCoefImpacto(QDialog, Ui_janela_coef_impacto):
    """
    Diálogo que exibe os coeficientes de impacto (CIA, CIV, CNF e φ),
    apresenta gráfico e memorial, e permite exportação dos resultados.
    """

    def __init__(self, gerenciador):
        super().__init__()
        self.setupUi(self)
        self.gerenciador = gerenciador
        self.fig_atual = None

        # Área de desenho do gráfico
        self.layout_desenho = QVBoxLayout(self.desenho)
        self.lbl_aguardando = QLabel("Aguardando Geração do Gráfico...")
        self.lbl_aguardando.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.layout_desenho.addWidget(self.lbl_aguardando)

        # Dicionários que armazenam as zonas dos coeficientes
        self.zonas_cia = {}
        self.zonas_civ = {}
        self.zonas_cnf = {}
        self.zonas_impacto = {}

        # Configuração da tabela de coeficientes
        self.table_coef.setColumnCount(2)
        self.table_coef.setHorizontalHeaderLabels(["Intervalo", "Valor do Coeficiente"])
        self.table_coef.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.table_coef.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.table_coef.verticalHeader().setVisible(False)
        self.table_coef.horizontalHeader().setStyleSheet("font-weight: bold;")

        fonte_tabela = self.table_coef.font()
        fonte_tabela.setPointSize(12)
        self.table_coef.setFont(fonte_tabela)
        self.table_coef.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)

        # Preenchimento da combo de coeficientes
        opcoes = [
            "Coeficiente de Impacto Adicional (CIA)",
            "Coeficiente de Impacto Vertical (CIV)",
            "Coeficiente do Número de Faixas (CNF)",
            "Coeficiente de Impacto Total (φ)"
        ]
        self.combo_coef.clear()
        self.combo_coef.addItems(opcoes)
        self.combo_coef.setCurrentIndex(3)  # Exibe φ por padrão

        # Conexões dos sinais
        self.combo_coef.currentIndexChanged.connect(self.atualizar_visualizacao)
        self.exportar.clicked.connect(self.abrir_dialogo_exportacao_grafico)
        self.exportar_tabela.clicked.connect(self.abrir_dialogo_exportacao_tabela)
        self.confirmar.clicked.connect(self.salvar_dados)
        self.cancelar.clicked.connect(self.reject)
        self.memorial_completo.clicked.connect(self._abrir_memorial_completo)
        self.manual.clicked.connect(self.abrir_manual)

        # Executa os cálculos e exibe o coeficiente padrão
        self.executar_calculo_impacto()
        self.atualizar_visualizacao()

    # -------------------------------------------------------------------------
    # Gerenciamento da janela
    # -------------------------------------------------------------------------
    def closeEvent(self, event):
        """Libera a figura do Matplotlib ao fechar o diálogo."""
        if self.fig_atual:
            plt.close(self.fig_atual)
            self.fig_atual = None
        super().closeEvent(event)

    # -------------------------------------------------------------------------
    # Cálculo dos coeficientes
    # -------------------------------------------------------------------------
    def executar_calculo_impacto(self):
        """Calcula as zonas de impacto a partir dos dados da superestrutura."""
        sup = self.gerenciador.get_superestrutura()
        sec = self.gerenciador.get_secao_transversal()

        if not sup or not sec:
            QMessageBox.critical(self, "Erro",
                                 "Superestrutura e Seção Transversal não encontradas.")
            self.reject()
            return

        try:
            calc = CalculadoraCoeficienteImpacto(sup, sec)
            self.zonas_cia = calc.get_zonas("CIA")
            self.zonas_civ = calc.get_zonas("CIV")
            self.zonas_cnf = calc.get_zonas("CNF")
            self.zonas_impacto = calc.get_zonas("IMPACTO")
        except Exception as e:
            QMessageBox.critical(self, "Erro de Cálculo",
                                 f"Ocorreu um erro no cálculo:\n{str(e)}")

    # -------------------------------------------------------------------------
    # Atualização da interface (tabela, HTML, gráfico)
    # -------------------------------------------------------------------------
    def atualizar_visualizacao(self):
        """
        Atualiza tabela, texto HTML e gráfico de acordo com o coeficiente
        selecionado na combo.
        """
        selecao = self.combo_coef.currentText()
        sup = self.gerenciador.get_superestrutura()
        sec = self.gerenciador.get_secao_transversal()

        # Determina a chave e o dicionário ativo
        if "CIA" in selecao:
            key_html = "cia"
            dict_ativo = self.zonas_cia
        elif "CIV" in selecao:
            key_html = "civ"
            dict_ativo = self.zonas_civ
        elif "CNF" in selecao:
            key_html = "cnf"
            dict_ativo = self.zonas_cnf
        else:  # Impacto total
            key_html = "impacto"
            dict_ativo = self.zonas_impacto

        # Memorial HTML
        try:
            html = gerar_html_memorial_coef(key_html)
            self.html_memorial_coef.setText(html)
            self.html_memorial_coef.setAlignment(Qt.AlignmentFlag.AlignCenter)
        except Exception as e:
            print(f"Aviso: Não foi possível carregar o HTML para {key_html}. Erro: {e}")

        # Tabela de zonas
        self.table_coef.setRowCount(0)
        for (xi, xf), valor in sorted(dict_ativo.items()):
            row = self.table_coef.rowCount()
            self.table_coef.insertRow(row)

            item_intervalo = QTableWidgetItem(f"De {xi:.2f} a {xf:.2f} m")
            item_intervalo.setTextAlignment(Qt.AlignmentFlag.AlignCenter)

            def formatar_numero(v):
                arredondado = round(v, 3)
                return f"{arredondado:.3f}".rstrip('0').rstrip('.')

            item_valor = QTableWidgetItem(formatar_numero(valor))
            item_valor.setTextAlignment(Qt.AlignmentFlag.AlignCenter)

            self.table_coef.setItem(row, 0, item_intervalo)
            self.table_coef.setItem(row, 1, item_valor)

        # Gráfico
        if self.fig_atual:
            plt.close(self.fig_atual)
            self.fig_atual = None

        for i in reversed(range(self.layout_desenho.count())):
            widget = self.layout_desenho.itemAt(i).widget()
            if widget:
                widget.setParent(None)

        try:
            self.fig_atual = desenhar_figura_coeficiente(sup, dict_ativo, "concreto_mista", key_html)
            self.fig_atual.set_size_inches(8.71, 3.11)
            self.layout_desenho.addWidget(FigureCanvas(self.fig_atual))
        except Exception as e:
            lbl_erro = QLabel(f"Erro ao gerar desenho:\n{str(e)}")
            lbl_erro.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.layout_desenho.addWidget(lbl_erro)

    # -------------------------------------------------------------------------
    # Exportações
    # -------------------------------------------------------------------------
    def abrir_dialogo_exportacao_grafico(self):
        """Exporta o gráfico atual em PNG ou DXF."""
        if not self.fig_atual:
            return
        dlg = DialogoExportacao(self)
        if dlg.exec():
            formato = dlg.formato_escolhido
            caminho, _ = QFileDialog.getSaveFileName(
                self, "Salvar Desenho", "", f"{formato.upper()} (*.{formato})")
            if caminho:
                try:
                    if formato == "png":
                        self.fig_atual.savefig(caminho, dpi=300, bbox_inches='tight')
                    else:
                        exportar_figura_para_dxf(self.fig_atual, caminho)
                    QMessageBox.information(self, "Sucesso", "Desenho exportado com sucesso!")
                except Exception as e:
                    QMessageBox.critical(self, "Erro na Exportação",
                                         f"Erro ao exportar gráfico:\n{str(e)}")

    def abrir_dialogo_exportacao_tabela(self):
        """Exporta a tabela de coeficientes nos formatos XLS, PDF ou TXT."""
        if self.table_coef.rowCount() == 0:
            QMessageBox.warning(self, "Aviso",
                                "A tabela está vazia, não há dados para exportar.")
            return

        dlg = DialogoExportacaoTabela(self)
        if dlg.exec():
            formato = dlg.formato_escolhido
            caminho, _ = QFileDialog.getSaveFileName(
                self, "Salvar Tabela", "", f"{formato.upper()} (*.{formato})")
            if caminho:
                matriz_dados = []
                for row in range(self.table_coef.rowCount()):
                    intervalo = self.table_coef.item(row, 0).text()
                    valor_str = self.table_coef.item(row, 1).text()
                    try:
                        valor = float(valor_str)
                    except ValueError:
                        valor = valor_str
                    matriz_dados.append([intervalo, valor])

                cabecalho = ["Intervalo", "Valor do Coeficiente"]
                titulo = self.combo_coef.currentText()

                try:
                    exportar_tabela(
                        matriz=matriz_dados,
                        titulo=titulo,
                        caminho_arquivo=caminho,
                        cabecalho=cabecalho
                    )
                    QMessageBox.information(self, "Sucesso", "Tabela exportada com sucesso!")
                except Exception as e:
                    QMessageBox.critical(self, "Erro na Exportação",
                                         f"Erro ao exportar tabela:\n{str(e)}")

    # -------------------------------------------------------------------------
    # Persistência dos dados
    # -------------------------------------------------------------------------
    def salvar_dados(self):
        """Salva as zonas de impacto no gerenciador de dados."""
        self.gerenciador.definir_coeficientes_impacto(
            self.zonas_cia,
            self.zonas_civ,
            self.zonas_cnf,
            self.zonas_impacto
        )
        self.accept()

    # -------------------------------------------------------------------------
    # Memorial completo
    # -------------------------------------------------------------------------
    def _abrir_memorial_completo(self):
        """Exibe o memorial descritivo completo dos coeficientes de impacto."""
        try:
            sup = self.gerenciador.get_superestrutura()
            sec = self.gerenciador.get_secao_transversal()
            if not sup or not sec:
                QMessageBox.critical(self, "Erro",
                                     "Dados da superestrutura não disponíveis.")
                return

            calc = CalculadoraCoeficienteImpacto(sup, sec)
            _, html_content = calc.obter_relatorio_resumido()

            dlg = LogicaJanelaMemorial(
                "Memorial de Cálculo – Coeficientes de Impacto (NBR 7188:2013)",
                html_content,
                parent=self
            )
            dlg.exec()
        except Exception as e:
            QMessageBox.critical(
                self,
                "Erro ao gerar memorial",
                f"Não foi possível gerar o memorial completo.\n\nDetalhes:\n{str(e)}"
            )

    # =========================================================================
    # Manual do usuário
    # =========================================================================
    def abrir_manual(self):
        """
        Abre o manual do software no PDFViewer na seção de coeficiente de impacto.

        Navega diretamente para a página 44 do manual (índice 43 em base 0,
        pois o PyMuPDF (fitz) indexa páginas a partir de zero).
        """
        pdf_path = resource_path(os.path.join("assets", "Manual Girder25 Dark.pdf"))
        viewer = PDFViewer(pdf_path, "Manual: COEFICIENTE DE IMPACTO")
        viewer.display_page(43)  # página 44 do manual → índice 43
        viewer.exec()