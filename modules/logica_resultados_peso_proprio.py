# ============================================================================
# Girder25 - logica_resultados_peso_proprio.py
# Autor: Fábio Henrique Sampaio Júnior
# Controlador das janelas de resultados de esforços e reações (peso próprio).
# ============================================================================

import os
import numpy as np
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QTableWidgetItem, QHeaderView,
    QFileDialog, QMessageBox, QSizePolicy
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QFont
import matplotlib.pyplot as plt
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas

from modules.logica_janela_def_superestrutura import DialogoExportacao
from modules.logica_resultado_trem_tipo_longarina import DialogoExportacaoTabela
from modules.exportar_dxf import exportar_figura_para_dxf
from modules.exportador import exportar_tabela
from modules.visualizador_pdf import PDFViewer
from modules.utils import resource_path

from ui.janela_resultados_esforcos import Ui_janela_resultados_esforcos
from ui.janela_resultados_reacoes import Ui_janela_resultados_reacoes
from modules.Calculadora_Elementos_Finitos import ativar_interatividade_simples
from modules.gerar_html import gerar_html_resultados_esforcos_calculos


class LogicaJanelaResultadosEsforcos(QDialog, Ui_janela_resultados_esforcos):
    """
    Janela de visualização detalhada de esforços (cortante ou momento fletor).
    Permite filtrar por passo, destacar valores extremos e exportar gráfico/tabela.
    """

    def __init__(self, titulo_janela: str, titulo_diagrama: str, titulo_tabela: str,
                 dados_tabela: list, figura_matplotlib, valores_destaque: list):
        super().__init__()
        self.setupUi(self)
        self.setWindowTitle(titulo_janela)
        self.groupbox_diagrama.setTitle(titulo_diagrama)
        self.groupbox_tabela.setTitle(titulo_tabela)

        self.dados_tabela = dados_tabela
        self.fig_atual = figura_matplotlib
        self.valores_destaque = valores_destaque

        self._configurar_interface()
        # Manual do usuário
        self.manual.clicked.connect(self.abrir_manual)

    def closeEvent(self, event):
        """Libera a figura ao fechar o diálogo."""
        if self.fig_atual:
            plt.close(self.fig_atual)
            self.fig_atual = None
        super().closeEvent(event)

    def _configurar_interface(self):
        """Renderiza o diagrama, configura controles e conecta sinais."""
        self._renderizar_figura()

        self.doubleSpinBox_passo_visualizacao.setValue(0.05)
        self.doubleSpinBox_passo_visualizacao.setSingleStep(0.05)
        self.doubleSpinBox_passo_visualizacao.setMinimum(0.05)
        self.doubleSpinBox_passo_visualizacao.setMaximum(5.00)
        self.doubleSpinBox_passo_visualizacao.setSuffix(" m")

        self.checkBox_arredondar.setChecked(False)
        self.checkBox_destacar.setChecked(True)

        self.atualizar_tabela.clicked.connect(self._atualizar_tabela)
        self.btn_ok.clicked.connect(self.accept)
        self.exportar.clicked.connect(self._exportar_grafico)
        self.exportar_tabela.clicked.connect(self._exportar_tabela)

        self._atualizar_tabela()

    def _renderizar_figura(self):
        """Exibe o diagrama Matplotlib no frame com interatividade."""
        layout_antigo = self.frame_diagrama.layout()
        if layout_antigo:
            while layout_antigo.count():
                item = layout_antigo.takeAt(0)
                if item.widget():
                    item.widget().deleteLater()
            layout_antigo.deleteLater()

        layout_figura = QVBoxLayout(self.frame_diagrama)
        layout_figura.setContentsMargins(0, 0, 0, 0)
        canvas = FigureCanvas(self.fig_atual)
        canvas.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        canvas.setFixedSize(canvas.sizeHint())
        layout_figura.addWidget(canvas, alignment=Qt.AlignmentFlag.AlignCenter)
        ativar_interatividade_simples(self.fig_atual, canvas)

    def _obter_secoes_criticas(self, cabecalho, linhas, tipo_janela):
        """Identifica as linhas de máximo e mínimo valor na tabela."""
        if not linhas:
            return {}
        idx_pos = cabecalho.index("Posição [m]") if "Posição [m]" in cabecalho else 0
        idx_val = len(cabecalho) - 1

        linha_max = max(linhas, key=lambda l: float(l[idx_val]))
        linha_min = min(linhas, key=lambda l: float(l[idx_val]))

        return {
            "Máximo": (f"({float(linha_max[idx_pos]):.2f} m)", float(linha_max[idx_val]), float(linha_max[idx_val])),
            "Mínimo": (f"({float(linha_min[idx_pos]):.2f} m)", float(linha_min[idx_val]), float(linha_min[idx_val]))
        }

    def _atualizar_tabela(self):
        """Reconstrói a tabela aplicando filtro de passo e destacando extremos."""
        if not self.dados_tabela or len(self.dados_tabela) < 2:
            return

        passo = self.doubleSpinBox_passo_visualizacao.value()
        arredondar = self.checkBox_arredondar.isChecked()
        destacar = self.checkBox_destacar.isChecked()

        cabecalho = self.dados_tabela[0]
        linhas_todas = self.dados_tabela[1:]
        tipo_janela = "Cortante" if "Cortante" in self.windowTitle() else "Momento"

        idx_pos = cabecalho.index("Posição [m]") if "Posição [m]" in cabecalho else 0

        # Filtragem por passo
        linhas_filtradas = []
        for linha in linhas_todas:
            pos = float(linha[idx_pos])
            rem = round(pos, 4) % passo
            if abs(rem) < 1e-3 or abs(rem - passo) < 1e-3:
                linhas_filtradas.append(linha)

        val_max_filt, val_min_filt = None, None
        if linhas_filtradas:
            valores = []
            for linha in linhas_filtradas:
                for c_idx, c_name in enumerate(cabecalho):
                    if "V" in c_name or "M" in c_name or "R" in c_name:
                        try:
                            valores.append(float(linha[c_idx]))
                        except ValueError:
                            pass
            if valores:
                val_max_filt = max(valores)
                val_min_filt = min(valores)

        tabela = self.tabela_esforcos
        tabela.clearContents()
        tabela.setColumnCount(len(cabecalho))
        tabela.setRowCount(len(linhas_filtradas))
        tabela.setHorizontalHeaderLabels(cabecalho)
        tabela.verticalHeader().setVisible(False)
        fonte_cab = tabela.horizontalHeader().font()
        fonte_cab.setBold(True)
        tabela.horizontalHeader().setFont(fonte_cab)

        # Oculta a coluna de posição (o usuário visualiza o passo diretamente no controle)
        tabela.setColumnHidden(idx_pos, True)

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

        tabela.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.label_resumo_visualizacao.setText(
            f"Visualizando: {len(linhas_filtradas)} de {len(linhas_todas)} pontos."
        )

        secoes_criticas = {tipo_janela: self._obter_secoes_criticas(cabecalho, linhas_todas, tipo_janela)}
        html = gerar_html_resultados_esforcos_calculos(secoes_criticas, "estatico", tipo_janela.lower())
        self.textEdit_resumo.setHtml(html)

    def _exportar_grafico(self):
        """Exporta o diagrama em PNG ou DXF."""
        if not self.fig_atual:
            return
        dlg = DialogoExportacao(self)
        if dlg.exec():
            formato = dlg.formato_escolhido
            caminho, _ = QFileDialog.getSaveFileName(self, "Salvar", "", f"{formato.upper()} (*.{formato})")
            if caminho:
                if formato == "png":
                    self.fig_atual.savefig(caminho, dpi=300, bbox_inches='tight')
                else:
                    exportar_figura_para_dxf(self.fig_atual, caminho)
                QMessageBox.information(self, "Sucesso", "Gráfico exportado!")

    def _exportar_tabela(self):
        """Exporta a tabela nos formatos XLS, PDF ou TXT."""
        if self.tabela_esforcos.rowCount() == 0:
            return
        dlg = DialogoExportacaoTabela(self)
        if dlg.exec():
            formato = dlg.formato_escolhido
            caminho, _ = QFileDialog.getSaveFileName(self, "Salvar", "", f"{formato.upper()} (*.{formato})")
            if caminho:
                matriz = []
                for row in range(self.tabela_esforcos.rowCount()):
                    linha = []
                    for col in range(self.tabela_esforcos.columnCount()):
                        item = self.tabela_esforcos.item(row, col)
                        try:
                            if item:
                                valor = float(item.text()) if ('.' in item.text() or 'e' in item.text().lower()) else int(item.text())
                            else:
                                valor = ""
                        except ValueError:
                            valor = item.text() if item else ""
                        linha.append(valor)
                    matriz.append(linha)
                cabecalho = [self.tabela_esforcos.horizontalHeaderItem(i).text() for i in range(self.tabela_esforcos.columnCount())]
                exportar_tabela(matriz=matriz, titulo=self.windowTitle(), caminho_arquivo=caminho, cabecalho=cabecalho)
                QMessageBox.information(self, "Sucesso", "Tabela exportada!")

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


class LogicaJanelaResultadosReacoes(QDialog, Ui_janela_resultados_reacoes):
    """
    Janela de visualização detalhada das reações de apoio.
    Permite destacar valores extremos e exportar a tabela.
    """

    def __init__(self, titulo_janela: str, dados_tabela: list, valores_destaque: list):
        super().__init__()
        self.setupUi(self)
        self.setWindowTitle(titulo_janela)
        self.dados_tabela = dados_tabela
        self.valores_destaque = valores_destaque
        self._configurar_interface()
        # Manual do usuário
        self.manual.clicked.connect(self.abrir_manual)

    def _configurar_interface(self):
        """Conecta os controles e realiza a primeira atualização da tabela."""
        self.checkBox_arredondar.setChecked(False)
        self.checkBox_destacar.setChecked(True)
        self.atualizar_tabela.clicked.connect(self._atualizar_tabela)
        self.btn_ok.clicked.connect(self.accept)
        self.exportar_tabela.clicked.connect(self._exportar_tabela)
        self._atualizar_tabela()

    def _obter_secoes_criticas(self, cabecalho, linhas):
        """Identifica as reações de máximo e mínimo valor."""
        if not linhas:
            return {}
        idx_nome = cabecalho.index("Apoio") if "Apoio" in cabecalho else 0
        idx_pos = cabecalho.index("Posição [m]") if "Posição [m]" in cabecalho else 1
        idx_val = cabecalho.index("R [kN]") if "R [kN]" in cabecalho else 2

        linha_max = max(linhas, key=lambda l: float(l[idx_val]))
        linha_min = min(linhas, key=lambda l: float(l[idx_val]))

        return {
            "Máximo": (f"Apoio {linha_max[idx_nome]} ({float(linha_max[idx_pos]):.2f} m)", float(linha_max[idx_val]), float(linha_max[idx_val])),
            "Mínimo": (f"Apoio {linha_min[idx_nome]} ({float(linha_min[idx_pos]):.2f} m)", float(linha_min[idx_val]), float(linha_min[idx_val]))
        }

    def _atualizar_tabela(self):
        """Reconstrói a tabela de reações com destaque dos valores extremos."""
        if not self.dados_tabela or len(self.dados_tabela) < 2:
            return
        arredondar = self.checkBox_arredondar.isChecked()
        destacar = self.checkBox_destacar.isChecked()

        cabecalho = self.dados_tabela[0]
        linhas_todas = self.dados_tabela[1:]

        val_max_filt, val_min_filt = None, None
        if linhas_todas:
            valores = []
            for linha in linhas_todas:
                for c_idx, c_name in enumerate(cabecalho):
                    if "R" in c_name:
                        try:
                            valores.append(float(linha[c_idx]))
                        except ValueError:
                            pass
            if valores:
                val_max_filt = max(valores)
                val_min_filt = min(valores)

        tabela = self.tabela_reacoes
        tabela.clearContents()
        tabela.setColumnCount(len(cabecalho))
        tabela.setRowCount(len(linhas_todas))
        tabela.setHorizontalHeaderLabels(cabecalho)
        tabela.verticalHeader().setVisible(False)
        fonte_cab = tabela.horizontalHeader().font()
        fonte_cab.setBold(True)
        tabela.horizontalHeader().setFont(fonte_cab)

        for row_idx, linha in enumerate(linhas_todas):
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
                elif "Apoio" in nome_col:
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

        tabela.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)

        secoes_criticas = {"Reações": self._obter_secoes_criticas(cabecalho, linhas_todas)}
        html = gerar_html_resultados_esforcos_calculos(secoes_criticas, "estatico", "reacoes")
        self.textEdit_resumo.setHtml(html)

    def _exportar_tabela(self):
        """Exporta a tabela de reações nos formatos XLS, PDF ou TXT."""
        if self.tabela_reacoes.rowCount() == 0:
            return
        dlg = DialogoExportacaoTabela(self)
        if dlg.exec():
            formato = dlg.formato_escolhido
            caminho, _ = QFileDialog.getSaveFileName(self, "Salvar", "", f"{formato.upper()} (*.{formato})")
            if caminho:
                matriz = []
                for row in range(self.tabela_reacoes.rowCount()):
                    linha = []
                    for col in range(self.tabela_reacoes.columnCount()):
                        item = self.tabela_reacoes.item(row, col)
                        try:
                            if item:
                                valor = float(item.text()) if ('.' in item.text() or 'e' in item.text().lower()) else int(item.text())
                            else:
                                valor = ""
                        except ValueError:
                            valor = item.text() if item else ""
                        linha.append(valor)
                    matriz.append(linha)
                cabecalho = [self.tabela_reacoes.horizontalHeaderItem(i).text() for i in range(self.tabela_reacoes.columnCount())]
                exportar_tabela(matriz=matriz, titulo=self.windowTitle(), caminho_arquivo=caminho, cabecalho=cabecalho)
                QMessageBox.information(self, "Sucesso", "Tabela exportada!")

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