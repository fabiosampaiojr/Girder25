# ============================================================================
# Girder25 - logica_janela_memorial_li.py
# Autor: Fábio Henrique Sampaio Júnior
# Controlador da janela de memorial de cálculo das Linhas de Influência.
# ============================================================================

import os
import numpy as np
from PyQt6.QtWidgets import (
    QDialog, QMessageBox, QVBoxLayout, QLabel,
    QFileDialog, QTableWidgetItem, QHeaderView
)
from PyQt6.QtCore import Qt
import matplotlib.pyplot as plt
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas

from ui.janela_memorial_li import Ui_janela_memorial_li
from modules.logica_janela_def_superestrutura import DialogoExportacao
from modules.exportar_dxf import exportar_figura_para_dxf
from modules.exportador import exportar_tabela
from modules.logica_resultado_trem_tipo_longarina import DialogoExportacaoTabela
from modules.gerar_html import gerar_html_xi2
from modules.logica_janela_memorial import LogicaJanelaMemorial
from modules.visualizador_pdf import PDFViewer
from modules.utils import resource_path


class InteractiveLICanvas(FigureCanvas):
    """
    Canvas interativo para diagramas de Linha de Influência (Courbon)
    e diagramas de carregamento (Seção AA e Seção BB).

    Recursos
    --------
    - Hover: crosshair vertical + marcador snap na curva + tooltip.
    - Scroll do mouse: zoom vertical centrado no cursor.
    - Duplo-clique / botão direito: restaura os limites Y originais.

    A figura deve possuir o atributo ``interactive_data`` com:
        'ax', 'c0', 'c1', 'longarina_i', 'tipo' ('li', 'aa' ou 'bb').
    """

    def __init__(self, figure):
        super().__init__(figure)
        self.figure   = figure
        self._idata   = getattr(figure, "interactive_data", None)
        self.ax       = None

        if figure.axes:
            self.ax = figure.axes[0]

        self._y_lim_orig = self.ax.get_ylim() if self.ax is not None else None

        self._vline   = None
        self._dot     = None
        self._tooltip = None
        self._setup_hover_elements()

        self.mpl_connect("motion_notify_event", self._on_move)
        self.mpl_connect("scroll_event",        self._on_scroll)
        self.mpl_connect("button_press_event",  self._on_click)

    # -------------------------------------------------------------------------
    # Elementos do hover
    # -------------------------------------------------------------------------
    def _setup_hover_elements(self) -> None:
        """Cria os elementos visuais do hover, iniciando invisíveis."""
        if self.ax is None or self._idata is None:
            return

        self._vline, = self.ax.plot(
            [], [], color="#FFA726", lw=0.9,
            linestyle="--", alpha=0.0, zorder=8, label="_nolegend_",
        )
        self._dot = self.ax.scatter(
            [], [], s=55, color="#A5D6A7",
            zorder=9, alpha=0.0, edgecolors="none",
        )
        self._tooltip = self.ax.text(
            0.018, 0.975, "",
            transform=self.ax.transAxes,
            fontsize=8.0, color="white",
            va="top", ha="left", linespacing=1.65,
            bbox=dict(
                boxstyle="round,pad=0.50",
                facecolor="#0d0d1a",
                edgecolor="#89b4fa",
                linewidth=0.9,
                alpha=0.0,
            ),
            zorder=20,
            visible=False,
        )

    # -------------------------------------------------------------------------
    # Callbacks de mouse
    # -------------------------------------------------------------------------
    def _on_move(self, event) -> None:
        """Atualiza crosshair, marcador e tooltip ao mover o mouse no painel."""
        if self.ax is None or self._idata is None or self._vline is None:
            return

        if event.inaxes is not self.ax or event.xdata is None:
            self._vline.set_alpha(0.0)
            self._dot.set_alpha(0.0)
            self._tooltip.set_visible(False)
            self.draw_idle()
            return

        x   = float(event.xdata)
        c0  = float(self._idata.get("c0", 0.0))
        c1  = float(self._idata.get("c1", 0.0))
        eta = c0 + c1 * x

        y_lo, y_hi = self.ax.get_ylim()
        self._vline.set_data([x, x], [y_lo, y_hi])
        self._vline.set_alpha(0.55)

        self._dot.set_offsets(np.array([[x, eta]]))
        self._dot.set_alpha(0.90)

        lbl_i = self._idata.get("longarina_i", "?")
        tipo  = self._idata.get("tipo", "li")

        if tipo == "bb":
            x_veh = self._idata.get("x_veh", None)
            veh_info = (f"\n  x_veh = {x_veh:.3f} m" if x_veh is not None else "")
            txt = (
                f"  x = {x:.3f} m{veh_info}\n"
                f"  η{lbl_i}(x) = {eta:+.4f}"
            )
        else:
            txt = (
                f"  x = {x:.3f} m\n"
                f"  η{lbl_i}(x) = {eta:+.4f}"
            )

        self._tooltip.set_text(txt)
        self._tooltip.get_bbox_patch().set_alpha(0.93)
        self._tooltip.set_visible(True)
        self.draw_idle()

    def _on_scroll(self, event) -> None:
        """Zoom vertical incremental centrado na posição Y do cursor."""
        if self.ax is None:
            return
        y_lo, y_hi = self.ax.get_ylim()
        y_c   = (float(event.ydata) if event.ydata is not None
                 else (y_lo + y_hi) / 2.0)
        fator = 0.85 if event.button == "up" else (1.0 / 0.85)
        new_lo = y_c - (y_c - y_lo) * fator
        new_hi = y_c + (y_hi - y_c) * fator
        if abs(new_hi - new_lo) < 1e-9:
            return
        self.ax.set_ylim(new_lo, new_hi)
        self.draw_idle()

    def _on_click(self, event) -> None:
        """Duplo-clique ou botão direito restaura os limites Y originais."""
        if self.ax is None or self._y_lim_orig is None:
            return
        if event.inaxes is self.ax and (event.dblclick or event.button == 3):
            self.ax.set_ylim(self._y_lim_orig)
            self.draw_idle()


class LogicaJanelaMemorialLI(QDialog, Ui_janela_memorial_li):
    """
    Diálogo do memorial de cálculo das Linhas de Influência.
    Exibe tabela de parâmetros, gráfico interativo e memorial completo.
    """

    def __init__(self, calculadora, parent=None):
        super().__init__(parent)
        self.setupUi(self)
        self.calculadora = calculadora
        self.fig_atual = None

        # Área de desenho
        self.layout_desenho = QVBoxLayout(self.desenho)

        # Conexões de sinais
        self.exportar.clicked.connect(self.abrir_dialogo_exportacao_grafico)
        self.exportar_tabela.clicked.connect(self.abrir_dialogo_exportacao_tabela)
        self.confirmar.clicked.connect(self.accept)
        self.memorial_completo.clicked.connect(self._abrir_memorial_completo)
        self.combo_longarina.currentIndexChanged.connect(self.atualizar_desenho)
        self.manual.clicked.connect(self.abrir_manual)

        # Preenche tabela e combo, desenha LI da primeira longarina
        self.preencher_tabela_e_combo()
        self.atualizar_desenho()

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
    # Preenchimento dos dados iniciais
    # -------------------------------------------------------------------------
    def preencher_tabela_e_combo(self):
        """
        Obtém a tabela resumo da calculadora, preenche a QTableWidget
        (colunas 0 a 3) e popula o combo de seleção da longarina.
        """
        dados_integrais = self.calculadora.get_tabela_resumo()
        cabecalhos = dados_integrais[0][:4]

        self.tabela_resumo.setColumnCount(len(cabecalhos))
        self.tabela_resumo.setHorizontalHeaderLabels(cabecalhos)
        self.tabela_resumo.verticalHeader().setVisible(False)
        self.tabela_resumo.horizontalHeader().setStyleSheet("font-weight: bold;")
        self.tabela_resumo.setStyleSheet("font-size: 12pt;")

        header = self.tabela_resumo.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)

        self.tabela_resumo.setRowCount(0)
        self.combo_longarina.clear()

        for linha_original in dados_integrais[1:]:
            row_idx = self.tabela_resumo.rowCount()
            self.tabela_resumo.insertRow(row_idx)

            i_val = str(linha_original[0])
            self.combo_longarina.addItem(i_val)

            for col_idx in range(4):
                valor = linha_original[col_idx]
                if isinstance(valor, float):
                    texto = f"{valor:.4f}"
                else:
                    texto = str(valor)

                item = QTableWidgetItem(texto)
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                item.setFlags(Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled)
                self.tabela_resumo.setItem(row_idx, col_idx, item)

        # Memorial Σxi²
        n = self.calculadora.n
        sum_xi2 = self.calculadora._sum_xi2
        html_memorial = gerar_html_xi2(n, sum_xi2)
        self.html_xi2.setText(html_memorial)
        self.html_xi2.setTextFormat(Qt.TextFormat.RichText)

    # -------------------------------------------------------------------------
    # Desenho da LI
    # -------------------------------------------------------------------------
    def atualizar_desenho(self):
        """Redesenha a Linha de Influência para a longarina selecionada."""
        texto_selecionado = self.combo_longarina.currentText()
        if not texto_selecionado:
            return

        i = int(texto_selecionado)

        # Limpa a área de desenho
        if self.fig_atual:
            plt.close(self.fig_atual)
            self.fig_atual = None

        for j in reversed(range(self.layout_desenho.count())):
            widget = self.layout_desenho.itemAt(j).widget()
            if widget:
                widget.setParent(None)

        try:
            self.fig_atual = self.calculadora.plotar_li(i)
            canvas = InteractiveLICanvas(self.fig_atual)
            canvas.setFixedSize(canvas.sizeHint())
            self.layout_desenho.addWidget(canvas)
        except Exception as e:
            lbl_erro = QLabel(f"Erro ao gerar desenho da Linha de Influência:\n{str(e)}")
            lbl_erro.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.layout_desenho.addWidget(lbl_erro)

    # -------------------------------------------------------------------------
    # Exportações
    # -------------------------------------------------------------------------
    def abrir_dialogo_exportacao_grafico(self):
        """Exporta o gráfico da LI em PNG ou DXF."""
        if not self.fig_atual:
            return
        dlg = DialogoExportacao(self)
        if dlg.exec():
            formato = dlg.formato_escolhido
            caminho, _ = QFileDialog.getSaveFileName(
                self, "Salvar Linha de Influência", "", f"{formato.upper()} (*.{formato})")
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
        """Exporta a tabela de LI nos formatos XLS, PDF ou TXT."""
        if self.tabela_resumo.rowCount() == 0:
            QMessageBox.warning(self, "Aviso", "A tabela está vazia, não há dados para exportar.")
            return

        dlg = DialogoExportacaoTabela(self)
        if dlg.exec():
            formato = dlg.formato_escolhido
            caminho, _ = QFileDialog.getSaveFileName(
                self, "Salvar Tabela de LI", "", f"{formato.upper()} (*.{formato})")
            if caminho:
                matriz_dados = []
                for row in range(self.tabela_resumo.rowCount()):
                    linha_dados = []
                    for col in range(self.tabela_resumo.columnCount()):
                        valor_str = self.tabela_resumo.item(row, col).text()
                        try:
                            if col == 0:
                                valor = int(valor_str)
                            elif col in (1, 2):
                                valor = float(valor_str)
                            else:
                                valor = valor_str
                        except ValueError:
                            valor = valor_str
                        linha_dados.append(valor)
                    matriz_dados.append(linha_dados)

                cabecalho = ["i", "xi [m]", "xi² [m²]", "η_ij"]
                titulo = "Memorial de Cálculo - Linhas de Influência de Courbon"

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
    # Memorial completo das LI
    # -------------------------------------------------------------------------
    def _abrir_memorial_completo(self):
        """Exibe o memorial descritivo completo das Linhas de Influência."""
        try:
            _, html_content = self.calculadora.obter_relatorio_lis()
            dlg = LogicaJanelaMemorial(
                "Memorial de Cálculo – Linhas de Influência (Courbon)",
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
        Abre o manual do software no PDFViewer na seção do memorial de
        cálculo da LI.

        Navega diretamente para a página 51 do manual (índice 50 em base 0,
        pois o PyMuPDF (fitz) indexa páginas a partir de zero).
        """
        pdf_path = resource_path(os.path.join("assets", "Manual Girder25 Dark.pdf"))
        viewer = PDFViewer(pdf_path, "Manual: MEMORIAL DE CÁLCULO DA LI")
        viewer.display_page(50)   # página 51 do manual → índice 50
        viewer.exec()