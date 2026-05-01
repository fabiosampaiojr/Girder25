# ============================================================================
# Girder25 - logica_resultado_trem_tipo_longarina.py
# Autor: Fábio Henrique Sampaio Júnior
# Controlador da janela de resultados da distribuição transversal do trem-tipo.
# ============================================================================

import os
from PyQt6.QtWidgets import (
    QDialog, QMessageBox, QVBoxLayout, QLabel,
    QFileDialog, QTableWidgetItem, QHeaderView, QComboBox,
    QPushButton, QHBoxLayout
)
from PyQt6.QtCore import Qt
import matplotlib.pyplot as plt
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas

from ui.janela_resultado_trem_tipo_longarina import Ui_janela_resultado_trem_tipo_longarina
from modules.Calculadora_Trem_Tipo_Longarina import Calculadora_Trem_Tipo_Longarina
from modules.desenho_esquema_cargas import desenhar_esquema_cargas
from modules.logica_janela_def_superestrutura import DialogoExportacao
from modules.exportar_dxf import exportar_figura_para_dxf
from modules.exportador import exportar_tabela
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


class LogicaResultadoTremTipoLongarina(QDialog, Ui_janela_resultado_trem_tipo_longarina):
    """
    Diálogo que exibe os resultados da distribuição transversal do trem-tipo
    (método de Engesser-Courbon), incluindo tabela resumo e esquema de cargas.
    """

    def __init__(self, gerenciador, trem_tipo, p_linha):
        super().__init__()
        self.setupUi(self)
        self.gerenciador = gerenciador
        self.trem_tipo = trem_tipo
        self.p_linha = p_linha
        self.fig_atual = None
        self.dados_criticos = None
        self.calculadora = None
        self.dados_tabela_completa = None

        # Área de desenho
        self.layout_desenho = QVBoxLayout(self.desenho)
        self.lbl_aguardando = QLabel("Aguardando Geração do Gráfico...")
        self.lbl_aguardando.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.layout_desenho.addWidget(self.lbl_aguardando)

        # Conexões de sinais
        self.exportar.clicked.connect(self.abrir_dialogo_exportacao_grafico)
        self.exportar_tabela.clicked.connect(self.abrir_dialogo_exportacao_tabela)
        self.confirmar.clicked.connect(self.salvar_dados)
        self.cancelar.clicked.connect(self.reject)

        if hasattr(self, 'abrir_calculo_li'):
            self.abrir_calculo_li.clicked.connect(self.abrir_janela_memorial_li)

        if hasattr(self, 'abrir_calculo_esforco'):
            self.abrir_calculo_esforco.clicked.connect(self.abrir_janela_memorial_esforco_resultante)

        # Manual do usuário
        self.manual.clicked.connect(self.abrir_manual)

        # Executa o cálculo automaticamente ao abrir
        self.executar_calculo()

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
    # Cálculo da distribuição transversal
    # -------------------------------------------------------------------------
    def executar_calculo(self):
        """Executa o cálculo de distribuição via Engesser-Courbon."""
        sec_super = self.gerenciador.get_secao_superestrutura()
        sec_trans = self.gerenciador.get_secao_transversal()

        if not sec_super or not sec_trans:
            QMessageBox.critical(self, "Erro",
                                 "Geometria da Superestrutura e Seção Transversal não encontradas.")
            self.reject()
            return

        try:
            self.calculadora = Calculadora_Trem_Tipo_Longarina(
                secao_superestrutura=sec_super,
                secao_transversal=sec_trans,
                trem_tipo=self.trem_tipo,
                p_linha=self.p_linha
            )

            self.dados_criticos = self.calculadora.get_configuracao_critica()
            dados_tabela = self.calculadora.get_tabela_resumo()
            self.dados_tabela_completa = dados_tabela

            self.preencher_tabela(dados_tabela)
            self.gerar_desenho_esquema()

        except Exception as e:
            QMessageBox.critical(self, "Erro de Cálculo",
                                 f"Ocorreu um erro no cálculo do trem-tipo:\n{str(e)}")
            self.reject()

    # -------------------------------------------------------------------------
    # Preenchimento da tabela resumo
    # -------------------------------------------------------------------------
    def preencher_tabela(self, dados_tabela):
        """Preenche a QTableWidget com os valores por longarina."""
        self.tabela_resumo.setColumnCount(4)
        cabecalhos_alvo = ["Longarina (i)", "q1 [kN/m]", "q2 [kN/m]", "Q [kN]"]
        self.tabela_resumo.setHorizontalHeaderLabels(cabecalhos_alvo)

        self.tabela_resumo.verticalHeader().setVisible(False)
        self.tabela_resumo.horizontalHeader().setStyleSheet("font-weight: bold;")

        header = self.tabela_resumo.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)

        self.tabela_resumo.setRowCount(0)

        # As colunas originais: 0(i), 1(xi), 2(xi²), 3(η), 4(q1), 5(q2), 6(Q)
        for linha_original in dados_tabela[1:]:
            row_idx = self.tabela_resumo.rowCount()
            self.tabela_resumo.insertRow(row_idx)

            valores_selecionados = [
                linha_original[0],  # i
                linha_original[4],  # q1
                linha_original[5],  # q2
                linha_original[6]   # Q
            ]

            for col_idx, valor in enumerate(valores_selecionados):
                if col_idx == 0:
                    texto = str(int(valor)) if isinstance(valor, (int, float)) else str(valor)
                else:
                    texto = f"{valor:.3f}"

                item = QTableWidgetItem(texto)
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                item.setFlags(Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled)
                self.tabela_resumo.setItem(row_idx, col_idx, item)

    # -------------------------------------------------------------------------
    # Desenho do esquema de cargas
    # -------------------------------------------------------------------------
    def gerar_desenho_esquema(self):
        """Desenha o esquema de cargas com os valores críticos."""
        if not self.dados_criticos:
            return

        if self.fig_atual:
            plt.close(self.fig_atual)
            self.fig_atual = None

        for i in reversed(range(self.layout_desenho.count())):
            widget = self.layout_desenho.itemAt(i).widget()
            if widget:
                widget.setParent(None)

        try:
            Q1 = self.dados_criticos["Q_kN"]
            q1 = self.dados_criticos["q1_kNm"]
            q2 = self.dados_criticos["q2_kNm"]

            Q1_rounded = round(Q1, 3)
            q1_rounded = round(q1, 3)
            q2_rounded = round(q2, 3)

            self.fig_atual = desenhar_esquema_cargas(
                Q1=Q1_rounded, q1=q1_rounded, q2=q2_rounded
            )
            self.layout_desenho.addWidget(FigureCanvas(self.fig_atual))

        except Exception as e:
            lbl_erro = QLabel(f"Erro ao gerar desenho das cargas:\n{str(e)}")
            lbl_erro.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.layout_desenho.addWidget(lbl_erro)

    # -------------------------------------------------------------------------
    # Exportações
    # -------------------------------------------------------------------------
    def abrir_dialogo_exportacao_grafico(self):
        """Exporta o esquema de cargas em PNG ou DXF."""
        if not self.fig_atual:
            return
        dlg = DialogoExportacao(self)
        if dlg.exec():
            formato = dlg.formato_escolhido
            caminho, _ = QFileDialog.getSaveFileName(
                self, "Salvar Esquema de Cargas", "", f"{formato.upper()} (*.{formato})")
            if caminho:
                try:
                    if formato == "png":
                        self.fig_atual.savefig(caminho, dpi=300, bbox_inches='tight')
                    else:
                        exportar_figura_para_dxf(self.fig_atual, caminho)
                    QMessageBox.information(self, "Sucesso", "Esquema exportado com sucesso!")
                except Exception as e:
                    QMessageBox.critical(self, "Erro na Exportação",
                                         f"Erro ao exportar gráfico:\n{str(e)}")

    def abrir_dialogo_exportacao_tabela(self):
        """Exporta a tabela resumo nos formatos XLS, PDF ou TXT."""
        if self.tabela_resumo.rowCount() == 0:
            QMessageBox.warning(self, "Aviso",
                                "A tabela está vazia, não há dados para exportar.")
            return

        dlg = DialogoExportacaoTabela(self)
        if dlg.exec():
            formato = dlg.formato_escolhido
            caminho, _ = QFileDialog.getSaveFileName(
                self, "Salvar Tabela de Resumo", "", f"{formato.upper()} (*.{formato})")
            if caminho:
                matriz_dados = []
                for row in range(self.tabela_resumo.rowCount()):
                    linha_dados = []
                    for col in range(self.tabela_resumo.columnCount()):
                        valor_str = self.tabela_resumo.item(row, col).text()
                        try:
                            valor = float(valor_str) if col > 0 else int(valor_str)
                        except ValueError:
                            valor = valor_str
                        linha_dados.append(valor)
                    matriz_dados.append(linha_dados)

                cabecalho = ["Longarina (i)", "q1 [kN/m]", "q2 [kN/m]", "Q [kN]"]
                titulo = "Resumo Trem-Tipo na Longarina"

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
        """Salva os resultados do trem-tipo no gerenciador de dados."""
        if self.calculadora and self.dados_tabela_completa:
            caso_critico = {
                "Q": self.dados_criticos["Q_kN"],
                "q1": self.dados_criticos["q1_kNm"],
                "q2": self.dados_criticos["q2_kNm"]
            }
            resumo_resultados = {}
            for linha in self.dados_tabela_completa[1:]:
                long_num = int(linha[0])
                resumo_resultados[f"Longarina {long_num}"] = {
                    "Q": linha[6],
                    "q1": linha[4],
                    "q2": linha[5]
                }
            self.gerenciador.definir_trem_tipo_longarina(caso_critico, resumo_resultados)
        self.accept()

    # -------------------------------------------------------------------------
    # Memoriais de cálculo auxiliares
    # -------------------------------------------------------------------------
    def abrir_janela_memorial_li(self):
        """Abre a janela de memorial de cálculo da Linha de Influência."""
        if not self.calculadora:
            QMessageBox.warning(self, "Aviso", "Os cálculos ainda não foram realizados.")
            return

        from modules.logica_janela_memorial_li import LogicaJanelaMemorialLI
        dialogo_li = LogicaJanelaMemorialLI(self.calculadora, parent=self)
        dialogo_li.exec()

    def abrir_janela_memorial_esforco_resultante(self):
        """Abre a janela de memorial de cálculo do Esforço Resultante (AA e BB)."""
        if not self.calculadora:
            QMessageBox.warning(self, "Aviso", "Os cálculos ainda não foram realizados.")
            return

        from modules.logica_janela_memorial_esforco_resultante import LogicaJanelaMemorialEsforcoResultante
        dialogo_esforco = LogicaJanelaMemorialEsforcoResultante(self.calculadora, parent=self)
        dialogo_esforco.exec()

    # =========================================================================
    # Manual do usuário
    # =========================================================================
    def abrir_manual(self):
        """
        Abre o manual do software no PDFViewer na seção de resumo da
        distribuição transversal.

        Navega diretamente para a página 48 do manual (índice 47 em base 0,
        pois o PyMuPDF (fitz) indexa páginas a partir de zero).
        """
        pdf_path = resource_path(os.path.join("assets", "Manual Girder25 Dark.pdf"))
        viewer = PDFViewer(pdf_path, "Manual: RESUMO DA DISTRIBUIÇÃO TRANSVERSAL")
        viewer.display_page(47)   # página 48 do manual → índice 47
        viewer.exec()