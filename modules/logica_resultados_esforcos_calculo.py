# ============================================================================
# Girder25 - logica_resultados_esforcos_calculo.py
# Autor: Fábio Henrique Sampaio Júnior
# Controlador das janelas de resultados de envoltória de esforços e reações
# (combinações de cálculo ELU/ELS).
# ============================================================================

import os
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QTableWidgetItem, QHeaderView,
    QFileDialog, QMessageBox, QSizePolicy
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor
import matplotlib.pyplot as plt
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas

from modules.logica_janela_def_superestrutura import DialogoExportacao
from modules.logica_resultado_trem_tipo_longarina import DialogoExportacaoTabela
from modules.exportar_dxf import exportar_figura_para_dxf
from modules.exportador import exportar_tabela
from modules.gerar_html import gerar_html_resultados_esforcos_calculos
from modules.Calculadora_Esforcos import ativar_interatividade
from modules.visualizador_pdf import PDFViewer
from modules.utils import resource_path

from ui.janela_resultados_esforcos import Ui_janela_resultados_esforcos
from ui.janela_resultados_reacoes import Ui_janela_resultados_reacoes


class LogicaJanelaResultadosEnvoltoria(QDialog, Ui_janela_resultados_esforcos):
    """
    Janela de visualização das envoltórias de esforços (cortante ou momento)
    resultantes das combinações de cálculo (ELU/ELS).
    """

    def __init__(self, titulo_janela: str, titulo_diagrama: str, titulo_tabela: str,
                 dados_tabela: list, figura_matplotlib, valores_destaque: list,
                 secoes_criticas: dict, tipo_esforco: str):
        super().__init__()
        self.setupUi(self)

        self.setWindowTitle(titulo_janela)
        self.groupbox_diagrama.setTitle(titulo_diagrama)
        self.groupbox_tabela.setTitle(titulo_tabela)

        self.dados_tabela    = dados_tabela
        self.fig_atual       = figura_matplotlib
        self.valores_destaque = valores_destaque  # [min_global, max_global]
        self.secoes_criticas  = secoes_criticas
        self.tipo_esforco     = tipo_esforco

        self.configurar_interface()
        # Manual do usuário
        self.manual.clicked.connect(self.abrir_manual)

    def closeEvent(self, event):
        """Libera a figura ao fechar o diálogo."""
        if self.fig_atual:
            plt.close(self.fig_atual)
            self.fig_atual = None
        super().closeEvent(event)

    def configurar_interface(self):
        """Renderiza o diagrama, configura controles e exibe o resumo HTML."""
        if self.frame_diagrama.layout():
            old_layout = self.frame_diagrama.layout()
            while old_layout.count():
                item = old_layout.takeAt(0)
                if item.widget():
                    item.widget().deleteLater()
            old_layout.deleteLater()

        layout_figura = QVBoxLayout(self.frame_diagrama)
        layout_figura.setContentsMargins(0, 0, 0, 0)

        canvas = FigureCanvas(self.fig_atual)
        w = int(self.fig_atual.get_figwidth()  * self.fig_atual.get_dpi())
        h = int(self.fig_atual.get_figheight() * self.fig_atual.get_dpi())
        canvas.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        canvas.setFixedSize(w, h)
        layout_figura.addWidget(canvas, alignment=Qt.AlignmentFlag.AlignCenter)

        ativar_interatividade(self.fig_atual, canvas)

        self.doubleSpinBox_passo_visualizacao.setSuffix(" m")
        self.doubleSpinBox_passo_visualizacao.setMinimum(0.05)
        self.doubleSpinBox_passo_visualizacao.setMaximum(5.00)
        self.doubleSpinBox_passo_visualizacao.setSingleStep(0.05)
        self.doubleSpinBox_passo_visualizacao.setValue(0.05)

        self.checkBox_destacar.setChecked(True)
        self.checkBox_arredondar.setChecked(False)

        html_resumo = gerar_html_resultados_esforcos_calculos(
            secoes_criticas=self.secoes_criticas,
            tipo_dado="calculo",
            janela=self.tipo_esforco.lower()
        )
        self.textEdit_resumo.setHtml(html_resumo)

        self.atualizar_tabela_esforcos()

        self.atualizar_tabela.clicked.connect(self.atualizar_tabela_esforcos)
        self.btn_ok.clicked.connect(self.accept)
        self.exportar.clicked.connect(self.abrir_dialogo_exportacao_grafico)
        self.exportar_tabela.clicked.connect(self.abrir_dialogo_exportacao_tabela)

    def atualizar_tabela_esforcos(self):
        """Reconstrói a tabela aplicando filtro de passo e destacando extremos."""
        passo      = self.doubleSpinBox_passo_visualizacao.value()
        arredondar = self.checkBox_arredondar.isChecked()
        destacar   = self.checkBox_destacar.isChecked()

        tabela = self.tabela_esforcos
        tabela.setSortingEnabled(False)

        if not self.dados_tabela or len(self.dados_tabela) < 2:
            return

        cabecalho       = self.dados_tabela[0]
        linhas_originais = self.dados_tabela[1:]

        linhas_filtradas = []
        for linha in linhas_originais:
            try:
                pos = float(linha[0])
                if abs(round(pos / passo) * passo - pos) < 1e-3:
                    linhas_filtradas.append(linha)
            except ValueError:
                pass

        tabela.setColumnCount(len(cabecalho))
        tabela.setRowCount(len(linhas_filtradas))
        tabela.setHorizontalHeaderLabels(cabecalho)

        tabela.verticalHeader().setVisible(False)
        fonte_cabecalho = tabela.horizontalHeader().font()
        fonte_cabecalho.setBold(True)
        tabela.horizontalHeader().setFont(fonte_cabecalho)

        header = tabela.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)

        # Oculta a coluna de posição
        if "Posição [m]" in cabecalho:
            idx_pos = cabecalho.index("Posição [m]")
            tabela.setColumnHidden(idx_pos, True)

        val_min_filt, val_max_filt = self.valores_destaque

        for row_idx, linha in enumerate(linhas_filtradas):
            cor_fundo = None
            if destacar:
                valores_esforco = []
                for c_idx, c_name in enumerate(cabecalho):
                    if "V" in c_name or "M" in c_name or "R" in c_name:
                        try:
                            valores_esforco.append(float(linha[c_idx]))
                        except ValueError:
                            pass

                if val_max_filt is not None and any(abs(v - val_max_filt) < 1e-6 for v in valores_esforco):
                    cor_fundo = QColor("#81c784")
                elif val_min_filt is not None and any(abs(v - val_min_filt) < 1e-6 for v in valores_esforco):
                    cor_fundo = QColor("#e57373")

            for col_idx, valor in enumerate(linha):
                nome_col = cabecalho[col_idx]

                if "Posição" in nome_col:
                    texto = f"{float(valor):.2f}"
                elif "Seção" in nome_col or "Apoio" in nome_col:
                    texto = str(valor)
                else:
                    try:
                        val_f = float(valor)
                        texto = f"{val_f:.0f}" if arredondar else f"{val_f:.3f}"
                    except ValueError:
                        texto = str(valor)

                item = QTableWidgetItem(texto)
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)

                if cor_fundo:
                    item.setBackground(cor_fundo)
                    item.setForeground(QColor("black"))
                    font = item.font()
                    font.setBold(True)
                    item.setFont(font)

                tabela.setItem(row_idx, col_idx, item)

        texto_label = (
            f'<html><head/><body><p align="center">'
            f'Visualizando: {len(linhas_filtradas)} de {len(linhas_originais)} pontos.'
            f'</p></body></html>'
        )
        self.label_resumo_visualizacao.setText(texto_label)

    def abrir_dialogo_exportacao_grafico(self):
        """Exporta o diagrama em PNG ou DXF."""
        if not self.fig_atual:
            return
        dlg = DialogoExportacao(self)
        if dlg.exec():
            formato = dlg.formato_escolhido
            caminho, _ = QFileDialog.getSaveFileName(self, "Salvar Diagrama Envoltória", "",
                                                     f"{formato.upper()} (*.{formato})")
            if caminho:
                try:
                    if formato == "png":
                        self.fig_atual.savefig(caminho, dpi=300, bbox_inches='tight')
                    else:
                        exportar_figura_para_dxf(self.fig_atual, caminho)
                    QMessageBox.information(self, "Sucesso", "Diagrama exportado com sucesso!")
                except Exception as e:
                    QMessageBox.critical(self, "Erro na Exportação", f"Erro ao exportar gráfico:\n{str(e)}")

    def abrir_dialogo_exportacao_tabela(self):
        """Exporta a tabela nos formatos XLS, PDF ou TXT."""
        if self.tabela_esforcos.rowCount() == 0:
            QMessageBox.warning(self, "Aviso", "A tabela está vazia, não há dados para exportar.")
            return

        dlg = DialogoExportacaoTabela(self)
        if dlg.exec():
            formato = dlg.formato_escolhido
            caminho, _ = QFileDialog.getSaveFileName(self, "Salvar Tabela Envoltória", "",
                                                     f"{formato.upper()} (*.{formato})")
            if caminho:
                matriz_dados = []
                for row in range(self.tabela_esforcos.rowCount()):
                    linha_dados = []
                    for col in range(self.tabela_esforcos.columnCount()):
                        item = self.tabela_esforcos.item(row, col)
                        if item is not None:
                            valor_str = item.text()
                            try:
                                valor = float(valor_str) if '.' in valor_str or 'e' in valor_str else int(valor_str)
                            except ValueError:
                                valor = valor_str
                        else:
                            valor = ""
                        linha_dados.append(valor)
                    matriz_dados.append(linha_dados)

                cabecalho = [self.tabela_esforcos.horizontalHeaderItem(i).text()
                             for i in range(self.tabela_esforcos.columnCount())]

                try:
                    exportar_tabela(matriz=matriz_dados, titulo=self.windowTitle(),
                                    caminho_arquivo=caminho, cabecalho=cabecalho)
                    QMessageBox.information(self, "Sucesso", "Tabela exportada com sucesso!")
                except Exception as e:
                    QMessageBox.critical(self, "Erro na Exportação", f"Erro ao exportar tabela:\n{str(e)}")

    # =========================================================================
    # Manual do usuário
    # =========================================================================
    def abrir_manual(self):
        """
        Abre o manual do software no PDFViewer na seção de resultados de
        cortante / momento.

        Navega diretamente para a página 82 do manual (índice 81 em base 0,
        pois o PyMuPDF (fitz) indexa páginas a partir de zero).
        """
        pdf_path = resource_path(os.path.join("assets", "Manual Girder25 Dark.pdf"))
        viewer = PDFViewer(pdf_path, "Manual: RESULTADOS CORTANTE / MOMENTO")
        viewer.display_page(81)   # página 82 do manual → índice 81
        viewer.exec()


class LogicaJanelaResultadosReacoesEnvoltoria(QDialog, Ui_janela_resultados_reacoes):
    """
    Janela de visualização das reações de apoio resultantes das combinações
    de cálculo (ELU/ELS).
    """

    def __init__(self, titulo_janela: str, dados_tabela: list, valores_destaque: list, secoes_criticas: dict):
        super().__init__()
        self.setupUi(self)

        self.setWindowTitle(titulo_janela)
        self.dados_tabela    = dados_tabela
        self.valores_destaque = valores_destaque
        self.secoes_criticas  = secoes_criticas

        self.configurar_interface()
        # Manual do usuário
        self.manual.clicked.connect(self.abrir_manual)

    def configurar_interface(self):
        """Configura os controles e exibe o resumo HTML inicial."""
        self.checkBox_destacar.setChecked(True)
        self.checkBox_arredondar.setChecked(False)

        html_resumo = gerar_html_resultados_esforcos_calculos(
            secoes_criticas=self.secoes_criticas,
            tipo_dado="calculo",
            janela="reacoes"
        )
        self.textEdit_resumo.setHtml(html_resumo)

        self.atualizar_tabela_reacoes()

        self.atualizar_tabela.clicked.connect(self.atualizar_tabela_reacoes)
        self.btn_ok.clicked.connect(self.accept)
        self.exportar_tabela.clicked.connect(self.abrir_dialogo_exportacao_tabela)

    def atualizar_tabela_reacoes(self):
        """Reconstrói a tabela de reações com destaque dos valores extremos."""
        arredondar = self.checkBox_arredondar.isChecked()
        destacar   = self.checkBox_destacar.isChecked()

        tabela = self.tabela_reacoes
        tabela.setSortingEnabled(False)

        if not self.dados_tabela or len(self.dados_tabela) < 2:
            return

        cabecalho = self.dados_tabela[0]
        linhas    = self.dados_tabela[1:]

        tabela.setColumnCount(len(cabecalho))
        tabela.setRowCount(len(linhas))
        tabela.setHorizontalHeaderLabels(cabecalho)

        tabela.verticalHeader().setVisible(False)
        fonte_cabecalho = tabela.horizontalHeader().font()
        fonte_cabecalho.setBold(True)
        tabela.horizontalHeader().setFont(fonte_cabecalho)

        header = tabela.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)

        val_min_filt, val_max_filt = self.valores_destaque

        for row_idx, linha in enumerate(linhas):
            cor_fundo = None
            if destacar:
                valores_esforco = []
                for c_idx, c_name in enumerate(cabecalho):
                    if "R" in c_name:
                        try:
                            valores_esforco.append(float(linha[c_idx]))
                        except ValueError:
                            pass

                if val_max_filt is not None and any(abs(v - val_max_filt) < 1e-6 for v in valores_esforco):
                    cor_fundo = QColor("#81c784")
                elif val_min_filt is not None and any(abs(v - val_min_filt) < 1e-6 for v in valores_esforco):
                    cor_fundo = QColor("#e57373")

            for col_idx, valor in enumerate(linha):
                nome_col = cabecalho[col_idx]

                if "Posição" in nome_col:
                    texto = f"{float(valor):.2f}"
                elif "Seção" in nome_col or "Apoio" in nome_col:
                    texto = str(valor)
                else:
                    try:
                        val_f = float(valor)
                        texto = f"{val_f:.0f}" if arredondar else f"{val_f:.3f}"
                    except ValueError:
                        texto = str(valor)

                item = QTableWidgetItem(texto)
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)

                if cor_fundo:
                    item.setBackground(cor_fundo)
                    item.setForeground(QColor("black"))
                    font = item.font()
                    font.setBold(True)
                    item.setFont(font)

                tabela.setItem(row_idx, col_idx, item)

    def abrir_dialogo_exportacao_tabela(self):
        """Exporta a tabela de reações nos formatos XLS, PDF ou TXT."""
        if self.tabela_reacoes.rowCount() == 0:
            QMessageBox.warning(self, "Aviso", "A tabela está vazia, não há dados para exportar.")
            return

        dlg = DialogoExportacaoTabela(self)
        if dlg.exec():
            formato = dlg.formato_escolhido
            caminho, _ = QFileDialog.getSaveFileName(self, "Salvar Tabela de Envoltória (Reações)", "",
                                                     f"{formato.upper()} (*.{formato})")
            if caminho:
                matriz_dados = []
                for row in range(self.tabela_reacoes.rowCount()):
                    linha_dados = []
                    for col in range(self.tabela_reacoes.columnCount()):
                        item = self.tabela_reacoes.item(row, col)
                        if item is not None:
                            valor_str = item.text()
                            try:
                                valor = float(valor_str) if '.' in valor_str or 'e' in valor_str else int(valor_str)
                            except ValueError:
                                valor = valor_str
                        else:
                            valor = ""
                        linha_dados.append(valor)
                    matriz_dados.append(linha_dados)

                cabecalho = [self.tabela_reacoes.horizontalHeaderItem(i).text()
                             for i in range(self.tabela_reacoes.columnCount())]

                try:
                    exportar_tabela(matriz=matriz_dados, titulo=self.windowTitle(),
                                    caminho_arquivo=caminho, cabecalho=cabecalho)
                    QMessageBox.information(self, "Sucesso", "Tabela exportada com sucesso!")
                except Exception as e:
                    QMessageBox.critical(self, "Erro na Exportação", f"Erro ao exportar tabela:\n{str(e)}")

    # =========================================================================
    # Manual do usuário
    # =========================================================================
    def abrir_manual(self):
        """
        Abre o manual do software no PDFViewer na seção de resultados de
        reações.

        Navega diretamente para a página 85 do manual (índice 84 em base 0,
        pois o PyMuPDF (fitz) indexa páginas a partir de zero).
        """
        pdf_path = resource_path(os.path.join("assets", "Manual Girder25 Dark.pdf"))
        viewer = PDFViewer(pdf_path, "Manual: RESULTADOS REAÇÕES")
        viewer.display_page(85)   # página 85 do manual → índice 84
        viewer.exec()