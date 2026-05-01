# ============================================================================
# Girder25 - logica_janela_memorial_esforco_resultante.py
# Autor: Fábio Henrique Sampaio Júnior
# Controlador do Memorial de Esforços Resultantes (Seções AA e BB).
# ============================================================================

import os
import numpy as np
from PyQt6.QtWidgets import (
    QDialog, QMessageBox, QVBoxLayout, QLabel,
    QFileDialog, QTableWidgetItem, QHeaderView,
    QComboBox, QPushButton, QHBoxLayout, QRadioButton, QButtonGroup
)
from PyQt6.QtCore import Qt
import matplotlib.pyplot as plt
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas

from ui.janela_memorial_esforco_resultante import Ui_janela_memorial_esforco_resultante
from modules.logica_janela_def_superestrutura import DialogoExportacao
from modules.exportar_dxf import exportar_figura_para_dxf
from modules.exportador import exportar_tabela
from modules.Calculadora_Trem_Tipo_Longarina import Calculadora_Trem_Tipo_Longarina
from modules.logica_janela_memorial import LogicaJanelaMemorial
from modules.visualizador_pdf import PDFViewer
from modules.utils import resource_path


# ============================================================================
# Canvas interativo para Seção AA e BB
# ============================================================================
class InteractiveLICanvas(FigureCanvas):
    """
    Canvas interativo para diagramas de Seção AA e Seção BB.

    Recursos
    --------
    - Hover: crosshair vertical + marcador snap + tooltip.
    - Scroll do mouse: zoom vertical centrado no cursor.
    - Duplo-clique / botão direito: restaura os limites Y originais.

    A figura deve possuir o atributo ``interactive_data`` com:
        'ax', 'c0', 'c1', 'longarina_i', 'tipo' ('aa' ou 'bb').
    """

    def __init__(self, figure):
        super().__init__(figure)
        self.figure   = figure
        self._idata   = getattr(figure, "interactive_data", None)
        self.ax       = figure.axes[0] if figure.axes else None
        self._y_lim_orig = self.ax.get_ylim() if self.ax is not None else None
        self._vline   = None
        self._dot     = None
        self._tooltip = None
        self._setup_hover_elements()
        self.mpl_connect("motion_notify_event", self._on_move)
        self.mpl_connect("scroll_event",        self._on_scroll)
        self.mpl_connect("button_press_event",  self._on_click)

    def _setup_hover_elements(self) -> None:
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
            bbox=dict(boxstyle="round,pad=0.50", facecolor="#0d0d1a",
                      edgecolor="#89b4fa", linewidth=0.9, alpha=0.0),
            zorder=20, visible=False,
        )

    def _on_move(self, event) -> None:
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
        tipo  = self._idata.get("tipo", "aa")
        if tipo == "bb":
            x_veh = self._idata.get("x_veh", None)
            veh_info = (f"\n  x_veh = {x_veh:.3f} m" if x_veh is not None else "")
            txt = f"  x = {x:.3f} m{veh_info}\n  η{lbl_i}(x) = {eta:+.4f}"
        else:
            txt = f"  x = {x:.3f} m\n  η{lbl_i}(x) = {eta:+.4f}"
        self._tooltip.set_text(txt)
        self._tooltip.get_bbox_patch().set_alpha(0.93)
        self._tooltip.set_visible(True)
        self.draw_idle()

    def _on_scroll(self, event) -> None:
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
        if self.ax is None or self._y_lim_orig is None:
            return
        if event.inaxes is self.ax and (event.dblclick or event.button == 3):
            self.ax.set_ylim(self._y_lim_orig)
            self.draw_idle()


class DialogoEscolhaDesenho(QDialog):
    """Diálogo para selecionar qual desenho exportar (Seção AA ou BB)."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Selecionar Desenho")
        self.setFixedSize(280, 150)
        self.desenho_escolhido = 1  # 1 para AA, 2 para BB

        layout = QVBoxLayout(self)

        lbl = QLabel("Qual desenho você deseja exportar?")
        layout.addWidget(lbl)

        self.grupo_botoes = QButtonGroup(self)
        self.radio_aa = QRadioButton("Desenho Seção AA (q1)")
        self.radio_aa.setChecked(True)
        self.grupo_botoes.addButton(self.radio_aa, 1)
        layout.addWidget(self.radio_aa)

        self.radio_bb = QRadioButton("Desenho Seção BB (q2 + Q)")
        self.grupo_botoes.addButton(self.radio_bb, 2)
        layout.addWidget(self.radio_bb)

        btn_layout = QHBoxLayout()
        btn_ok = QPushButton("Confirmar")
        btn_cancel = QPushButton("Cancelar")

        btn_ok.clicked.connect(self.aceitar)
        btn_cancel.clicked.connect(self.reject)

        btn_layout.addWidget(btn_ok)
        btn_layout.addWidget(btn_cancel)
        layout.addLayout(btn_layout)

    def aceitar(self):
        self.desenho_escolhido = self.grupo_botoes.checkedId()
        self.accept()


class DialogoExportacaoTabelaResumo(QDialog):
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


class LogicaJanelaMemorialEsforcoResultante(QDialog, Ui_janela_memorial_esforco_resultante):
    """
    Diálogo do memorial de esforços resultantes.
    Exibe tabela de integrais e cargas, além dos diagramas interativos
    das Seções AA e BB para cada longarina.
    """

    def __init__(self, calculadora: Calculadora_Trem_Tipo_Longarina, parent=None):
        super().__init__(parent)
        self.setupUi(self)
        self.calculadora = calculadora

        self.fig_aa = None
        self.fig_bb = None

        # Áreas de desenho
        self.layout_desenho_1 = QVBoxLayout(self.desenho_1)
        self.layout_desenho_2 = QVBoxLayout(self.desenho_2)

        # Conexões
        self.confirmar.clicked.connect(self.accept)
        self.exportar_tabela.clicked.connect(self.abrir_dialogo_exportacao_tabela)
        self.exportar.clicked.connect(self.abrir_dialogo_exportacao_grafico)
        self.combo_longarina.currentIndexChanged.connect(self.atualizar_desenhos)
        self.combo_exibir_anotacao.stateChanged.connect(self.atualizar_desenhos)
        self.memorial_completo.clicked.connect(self._abrir_memorial_completo)
        self.manual.clicked.connect(self.abrir_manual)

        # Inicialização
        self.preencher_tabela()
        self.preencher_combo()

    # -------------------------------------------------------------------------
    # Gerenciamento da janela
    # -------------------------------------------------------------------------
    def closeEvent(self, event):
        """Libera ambas as figuras do Matplotlib ao fechar o diálogo."""
        for fig in (self.fig_aa, self.fig_bb):
            if fig:
                plt.close(fig)
        self.fig_aa = None
        self.fig_bb = None
        super().closeEvent(event)

    # -------------------------------------------------------------------------
    # Preenchimento da tabela
    # -------------------------------------------------------------------------
    def preencher_tabela(self):
        """Obtém os dados da calculadora e preenche a tabela de resumo."""
        dados_completos = self.calculadora.get_resumo_calculo()
        if not dados_completos or len(dados_completos) < 2:
            return

        cabecalho = dados_completos[0]
        linhas_dados = dados_completos[1:]

        self.tabela_resumo.setColumnCount(len(cabecalho))
        self.tabela_resumo.setHorizontalHeaderLabels(cabecalho)
        self.tabela_resumo.verticalHeader().setVisible(False)
        self.tabela_resumo.horizontalHeader().setStyleSheet("font-weight: bold;")

        header = self.tabela_resumo.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(len(cabecalho) - 1, QHeaderView.ResizeMode.Stretch)

        self.tabela_resumo.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.tabela_resumo.setRowCount(0)

        for row_idx, linha in enumerate(linhas_dados):
            self.tabela_resumo.insertRow(row_idx)
            for col_idx, valor in enumerate(linha):
                if isinstance(valor, float):
                    texto = f"{valor:.3f}"
                else:
                    texto = str(valor)

                item = QTableWidgetItem(texto)
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                item.setFlags(Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled)
                self.tabela_resumo.setItem(row_idx, col_idx, item)

    # -------------------------------------------------------------------------
    # Combo de longarinas
    # -------------------------------------------------------------------------
    def preencher_combo(self):
        """Preenche o combo com os índices das longarinas disponíveis."""
        self.combo_longarina.blockSignals(True)
        self.combo_longarina.clear()

        dados_completos = self.calculadora.get_resumo_calculo()
        if len(dados_completos) > 1:
            for linha in dados_completos[1:]:
                i_valor = str(int(linha[0])) if isinstance(linha[0], (int, float)) else str(linha[0])
                self.combo_longarina.addItem(f"Longarina {i_valor}", userData=int(linha[0]))

        self.combo_longarina.blockSignals(False)

        if self.combo_longarina.count() > 0:
            self.atualizar_desenhos()

    # -------------------------------------------------------------------------
    # Desenhos das seções AA e BB
    # -------------------------------------------------------------------------
    def atualizar_desenhos(self):
        """
        Redesenha os diagramas AA e BB para a longarina selecionada,
        respeitando a opção de exibição de anotação.
        """
        if self.combo_longarina.count() == 0:
            return

        i_selecionado = self.combo_longarina.currentData()
        if not i_selecionado:
            return

        # Limpa área AA
        if self.fig_aa:
            plt.close(self.fig_aa)
            self.fig_aa = None
        for j in reversed(range(self.layout_desenho_1.count())):
            widget = self.layout_desenho_1.itemAt(j).widget()
            if widget:
                widget.setParent(None)

        # Limpa área BB
        if self.fig_bb:
            plt.close(self.fig_bb)
            self.fig_bb = None
        for j in reversed(range(self.layout_desenho_2.count())):
            widget = self.layout_desenho_2.itemAt(j).widget()
            if widget:
                widget.setParent(None)

        try:
            exibir_anotacao = self.combo_exibir_anotacao.isChecked()

            self.fig_aa = self.calculadora.plotar_secao_AA(
                i=i_selecionado, exibir_anotacao=exibir_anotacao
            )
            canvas_aa = InteractiveLICanvas(self.fig_aa)
            canvas_aa.setFixedSize(canvas_aa.sizeHint())
            self.layout_desenho_1.addWidget(canvas_aa)

            self.fig_bb = self.calculadora.plotar_secao_BB(
                i=i_selecionado, exibir_anotacao=exibir_anotacao
            )
            canvas_bb = InteractiveLICanvas(self.fig_bb)
            canvas_bb.setFixedSize(canvas_bb.sizeHint())
            self.layout_desenho_2.addWidget(canvas_bb)

        except Exception as e:
            QMessageBox.warning(self, "Erro de Desenho",
                                f"Ocorreu um erro ao gerar os gráficos:\n{str(e)}")

    # -------------------------------------------------------------------------
    # Exportações
    # -------------------------------------------------------------------------
    def abrir_dialogo_exportacao_grafico(self):
        """Exporta o gráfico selecionado (AA ou BB) em PNG ou DXF."""
        if not self.fig_aa and not self.fig_bb:
            QMessageBox.warning(self, "Aviso", "Não há desenhos gerados para exportar.")
            return

        dlg_escolha = DialogoEscolhaDesenho(self)
        if not dlg_escolha.exec():
            return

        figura_alvo = self.fig_aa if dlg_escolha.desenho_escolhido == 1 else self.fig_bb
        nome_sugerido = "Secao_AA" if dlg_escolha.desenho_escolhido == 1 else "Secao_BB"

        dlg_formato = DialogoExportacao(self)
        if dlg_formato.exec():
            formato = dlg_formato.formato_escolhido
            caminho, _ = QFileDialog.getSaveFileName(
                self, f"Salvar {nome_sugerido}",
                f"{nome_sugerido}.{formato}",
                f"{formato.upper()} (*.{formato})"
            )
            if caminho:
                try:
                    if formato == "png":
                        figura_alvo.savefig(caminho, dpi=300, bbox_inches='tight')
                    else:
                        exportar_figura_para_dxf(figura_alvo, caminho)
                    QMessageBox.information(self, "Sucesso", "Gráfico exportado com sucesso!")
                except Exception as e:
                    QMessageBox.critical(self, "Erro na Exportação",
                                         f"Erro ao exportar gráfico:\n{str(e)}")

    def abrir_dialogo_exportacao_tabela(self):
        """Exporta a tabela resumo nos formatos XLS, PDF ou TXT."""
        if self.tabela_resumo.rowCount() == 0:
            QMessageBox.warning(self, "Aviso", "A tabela está vazia.")
            return

        dlg = DialogoExportacaoTabelaResumo(self)
        if dlg.exec():
            formato = dlg.formato_escolhido
            caminho, _ = QFileDialog.getSaveFileName(
                self, "Salvar Memorial de Esforços", "", f"{formato.upper()} (*.{formato})"
            )
            if caminho:
                matriz_dados = []
                for row in range(self.tabela_resumo.rowCount()):
                    linha_dados = []
                    for col in range(self.tabela_resumo.columnCount()):
                        valor_str = self.tabela_resumo.item(row, col).text()
                        try:
                            valor = float(valor_str) if '.' in valor_str else int(valor_str)
                        except ValueError:
                            valor = valor_str
                        linha_dados.append(valor)
                    matriz_dados.append(linha_dados)

                cabecalho = [
                    self.tabela_resumo.horizontalHeaderItem(i).text()
                    for i in range(self.tabela_resumo.columnCount())
                ]
                titulo = "Memorial de Esforços Resultantes"

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
    # Memorial completo
    # -------------------------------------------------------------------------
    def _abrir_memorial_completo(self):
        """Exibe o memorial descritivo completo do trem-tipo longitudinal."""
        try:
            _, html_content = self.calculadora.obter_relatorio_trem_tipo()
            dlg = LogicaJanelaMemorial(
                "Memorial de Cálculo – Trem-Tipo Longitudinal Equivalente",
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
        cálculo do esforço resultante.

        Navega diretamente para a página 52 do manual (índice 51 em base 0,
        pois o PyMuPDF (fitz) indexa páginas a partir de zero).
        """
        pdf_path = resource_path(os.path.join("assets", "Manual Girder25 Dark.pdf"))
        viewer = PDFViewer(pdf_path, "Manual: MEMORIAL DE CÁLCULO DO ESFORÇO RESULTANTE")
        viewer.display_page(51)   # página 52 do manual → índice 51
        viewer.exec()