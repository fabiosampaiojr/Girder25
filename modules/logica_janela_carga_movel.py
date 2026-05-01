# ============================================================================
# Girder25 - logica_janela_carga_movel.py
# Autor: Fábio Henrique Sampaio Júnior
# Controlador da análise da carga móvel (envoltórias de esforços).
# ============================================================================

from __future__ import annotations

import time
import os

import matplotlib.pyplot as plt
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas

from PyQt6.QtWidgets import (
    QDialog,
    QDoubleSpinBox,
    QHeaderView,
    QLabel,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QTableWidgetItem,
    QVBoxLayout,
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal

from ui.janela_carga_movel import Ui_janela_carga_movel

from modules.Calculadora_Carga_Movel import CalculadoraCargaMovel
from modules.desenho_dcl_coef import desenhar_figura_coeficiente
from modules.desenho_esquema_cargas import desenhar_esquema_cargas

from modules.gerar_html import (
    gerar_html_trem_tipo,
    html_definir_cargas,
    gerar_html_resultados_esforcos_calculos,
)

from modules.logica_resultados_carga_movel import (
    LogicaJanelaResultadosEnvoltoria,
    LogicaJanelaResultadosReacoesCargaMovel,
)
from modules.visualizador_pdf import PDFViewer
from modules.utils import resource_path


# ============================================================================
# WORKER E DIÁLOGO DE PROGRESSO
# ============================================================================

class _WorkerCalculo(QThread):
    """Executa CalculadoraCargaMovel.calcular() em thread separada."""

    concluido = pyqtSignal(list, list, list, float)   # reacoes, cortante, momento, elapsed_s
    erro      = pyqtSignal(str)

    def __init__(self, calculadora: CalculadoraCargaMovel):
        super().__init__()
        self._calculadora = calculadora

    def run(self):
        try:
            t0 = time.perf_counter()
            tabela_r, tabela_c, tabela_m = self._calculadora.calcular()
            elapsed = time.perf_counter() - t0
            self.concluido.emit(tabela_r, tabela_c, tabela_m, elapsed)
        except Exception as exc:
            self.erro.emit(str(exc))


class _DialogoProgresso(QDialog):
    """
    Janela modal que gerencia a escolha do modo de cálculo (Rápido/Preciso),
    exibe barra de progresso e, ao final, um resumo das métricas.
    """

    modo_selecionado = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Cálculo de Carga Móvel")
        self.setWindowFlags(
            Qt.WindowType.Dialog |
            Qt.WindowType.CustomizeWindowHint |
            Qt.WindowType.WindowTitleHint
        )
        self.setMinimumWidth(440)
        self.setModal(True)
        self._calculando = False

        layout = QVBoxLayout(self)
        layout.setSpacing(14)
        layout.setContentsMargins(28, 28, 28, 20)

        # Tela de seleção de modo
        self._lbl_instrucao = QLabel("Escolha a densidade da malha de cálculo:")
        self._lbl_instrucao.setAlignment(Qt.AlignmentFlag.AlignCenter)
        fonte = self._lbl_instrucao.font()
        fonte.setPointSize(11)
        fonte.setBold(True)
        self._lbl_instrucao.setFont(fonte)
        layout.addWidget(self._lbl_instrucao)

        self._btn_rapido = QPushButton(
            "⚡ Modo Rápido (≤ 5s)\nIdeal para iterações e pré-dimensionamento"
        )
        self._btn_rapido.setMinimumHeight(50)
        self._btn_rapido.clicked.connect(self._selecionar_rapido)
        layout.addWidget(self._btn_rapido)

        self._btn_preciso = QPushButton(
            "🎯 Modo Preciso (≤ 60s)\nFidelidade máxima para memoriais finais"
        )
        self._btn_preciso.setMinimumHeight(50)
        self._btn_preciso.clicked.connect(self._selecionar_preciso)
        layout.addWidget(self._btn_preciso)

        # Tela de progresso
        self._lbl_status = QLabel("Calculando Envoltórias...")
        self._lbl_status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._lbl_status.setFont(fonte)
        self._lbl_status.setVisible(False)
        layout.addWidget(self._lbl_status)

        self._progress = QProgressBar()
        self._progress.setRange(0, 0)
        self._progress.setFixedHeight(12)
        self._progress.setVisible(False)
        layout.addWidget(self._progress)

        # Tela de resultado
        self._lbl_metricas = QLabel("")
        self._lbl_metricas.setAlignment(Qt.AlignmentFlag.AlignLeft)
        self._lbl_metricas.setWordWrap(True)
        self._lbl_metricas.setVisible(False)
        layout.addWidget(self._lbl_metricas)

        self._btn_ok = QPushButton("OK")
        self._btn_ok.setMinimumWidth(100)
        self._btn_ok.clicked.connect(self.accept)
        self._btn_ok.setVisible(False)
        layout.addWidget(self._btn_ok, alignment=Qt.AlignmentFlag.AlignCenter)

    def _selecionar_rapido(self):
        self._iniciar_interface_calculo()
        self.modo_selecionado.emit("Rápido")

    def _selecionar_preciso(self):
        self._iniciar_interface_calculo()
        self.modo_selecionado.emit("Preciso")

    def _iniciar_interface_calculo(self):
        self._calculando = True
        self._lbl_instrucao.setVisible(False)
        self._btn_rapido.setVisible(False)
        self._btn_preciso.setVisible(False)
        self._lbl_status.setVisible(True)
        self._progress.setVisible(True)
        self.adjustSize()

    def mostrar_sucesso(self, metricas_texto: str) -> None:
        self._calculando = False
        self._lbl_status.setText("✓  Envoltórias Calculadas com Sucesso!")
        self._progress.setVisible(False)
        self._lbl_metricas.setText(metricas_texto)
        self._lbl_metricas.setVisible(True)
        self._btn_ok.setVisible(True)
        self._btn_ok.setDefault(True)
        self._btn_ok.setFocus()
        self.adjustSize()

    def mostrar_erro(self, mensagem: str) -> None:
        self._calculando = False
        self._lbl_instrucao.setVisible(False)
        self._btn_rapido.setVisible(False)
        self._btn_preciso.setVisible(False)
        self._progress.setVisible(False)
        self._lbl_status.setText("✗  Erro no Cálculo")
        self._lbl_status.setVisible(True)
        self._lbl_metricas.setText(mensagem)
        self._lbl_metricas.setVisible(True)
        self._btn_ok.setVisible(True)
        self._btn_ok.setDefault(True)
        self._btn_ok.setFocus()
        self.adjustSize()

    def closeEvent(self, event):
        if self._calculando:
            event.ignore()
        else:
            super().closeEvent(event)


# ============================================================================
# CONTROLADOR PRINCIPAL
# ============================================================================

class LogicaJanelaCargaMovel(QDialog, Ui_janela_carga_movel):
    """
    Diálogo para análise da carga móvel.
    Permite configurar os coeficientes de impacto, o trem-tipo e obter
    envoltórias de esforços (cortante e momento fletor) via MEF.
    """

    def __init__(self, gerenciador):
        super().__init__()
        self.setupUi(self)
        self._gerenciador = gerenciador

        self._superestrutura = gerenciador.get_superestrutura()
        self._secao_super    = gerenciador.get_secao_superestrutura()
        self._coef_impacto   = gerenciador.get_coeficientes_impacto()
        self._trem_longarina = gerenciador.get_trem_tipo_longarina()

        self._L_total: float = self._extrair_L_total()

        self._dict_coef: dict  = {}
        self._trem_tipo: dict  = {}

        self._fig_coef:    plt.Figure | None = None
        self._fig_esquema: plt.Figure | None = None

        self._calculadora:     CalculadoraCargaMovel | None = None
        self._tabela_reacoes:  list = []
        self._tabela_cortante: list = []
        self._tabela_momento:  list = []
        self._fig_cortante:    plt.Figure | None = None
        self._fig_momento:     plt.Figure | None = None

        self.valores_limites = {}

        self._bloqueando_sinais_tabela: bool = False

        self._worker:  _WorkerCalculo    | None = None
        self._dialogo: _DialogoProgresso | None = None

        self._layout_desenho  = QVBoxLayout(self.desenho)
        self._layout_desenho2 = QVBoxLayout(self.desenho_2)

        self._configurar_spinboxes_trem()
        self._configurar_sinais()
        self._inicializar_estados_ui()

        self.html_resultados_esforcos.setPlainText("Aguardando Cálculos")

        self._exibir_placeholder_desenho()
        self._exibir_placeholder_desenho2()

        self._preencher_table_coef_automatica()
        self._atualizar_dict_coef()
        self._atualizar_dict_trem_tipo()

    # -------------------------------------------------------------------------
    # Gerenciamento da janela
    # -------------------------------------------------------------------------
    def closeEvent(self, event):
        """Libera todas as figuras do Matplotlib ao fechar o diálogo."""
        for fig in (self._fig_coef, self._fig_esquema, self._fig_cortante, self._fig_momento):
            if fig:
                plt.close(fig)
        self._fig_coef = None
        self._fig_esquema = None
        self._fig_cortante = None
        self._fig_momento = None
        super().closeEvent(event)

    # -------------------------------------------------------------------------
    # Inicialização e configuração da UI
    # -------------------------------------------------------------------------
    def _extrair_L_total(self) -> float:
        if not self._coef_impacto:
            return 0.0
        zonas = getattr(self._coef_impacto, "zonas_impacto", {})
        if not zonas:
            return 0.0
        return max(xf for (_, xf) in zonas.keys())

    def _configurar_spinboxes_trem(self):
        self.spin_q.setRange(1.0, 200.0)
        self.spin_q.setSingleStep(1.0)
        self.spin_q.setDecimals(3)
        self.spin_q.setValue(100.0)
        self.spin_q.setSuffix(" kN")

        self.spin_q1.setRange(0.0, 30.0)
        self.spin_q1.setSingleStep(0.5)
        self.spin_q1.setDecimals(3)
        self.spin_q1.setValue(5.0)
        self.spin_q1.setSuffix(" kN/m")

        self.spin_q2.setRange(0.0, 30.0)
        self.spin_q2.setSingleStep(0.5)
        self.spin_q2.setDecimals(3)
        self.spin_q2.setValue(5.0)
        self.spin_q2.setSuffix(" kN/m")

    def _configurar_sinais(self):
        self.coef_automatico.toggled.connect(self._on_coef_radio_alterado)
        self.coef_manual.toggled.connect(self._on_coef_radio_alterado)

        self.trem_critico.toggled.connect(self._on_trem_radio_alterado)
        self.trem_longarina.toggled.connect(self._on_trem_radio_alterado)
        self.trem_carga.toggled.connect(self._on_trem_radio_alterado)

        self.combo_longarina.currentTextChanged.connect(self._on_combo_longarina_alterado)

        self.spin_q.valueChanged.connect(self._on_spin_trem_alterado)
        self.spin_q1.valueChanged.connect(self._on_spin_trem_alterado)
        self.spin_q2.valueChanged.connect(self._on_spin_trem_alterado)

        self.calcular.clicked.connect(self._processar_calculos)
        self.botao_cortante.clicked.connect(self._abrir_janela_cortante)
        self.botao_momento.clicked.connect(self._abrir_janela_momento)
        self.botao_reacoes.clicked.connect(self._abrir_janela_reacoes)
        self.cancelar.clicked.connect(self.reject)
        self.confirmar.clicked.connect(self._acao_confirmar)

        self.atualizar_qframe_desenho.clicked.connect(self._on_atualizar_desenho)
        self.atualizar_q_frame_desenho_2.clicked.connect(self._on_atualizar_desenho2)

        # Manual do usuário
        self.manual.clicked.connect(self.abrir_manual)

    def _inicializar_estados_ui(self):
        self.coef_automatico.setChecked(True)
        self.trem_critico.setChecked(True)

        self._preencher_combo_longarina()

        self.botao_cortante.setEnabled(False)
        self.botao_momento.setEnabled(False)
        self.botao_reacoes.setEnabled(False)

        self._aplicar_estado_grupo_coef()
        self._aplicar_estado_grupo_trem()

    # -------------------------------------------------------------------------
    # Gerenciamento da tabela de coeficientes
    # -------------------------------------------------------------------------
    def _preencher_table_coef_automatica(self):
        zonas  = getattr(self._coef_impacto, "zonas_impacto", {}) if self._coef_impacto else {}
        tabela = self.table_coef

        tabela.clear()
        tabela.setColumnCount(2)
        tabela.setHorizontalHeaderLabels(["Intervalo", "Valor do Coeficiente"])
        tabela.setRowCount(len(zonas))
        tabela.verticalHeader().setVisible(False)

        for row, ((x_ini, x_fim), phi) in enumerate(sorted(zonas.items())):
            item_intervalo = QTableWidgetItem(f"{x_ini:.3f} m – {x_fim:.3f} m")
            item_intervalo.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            item_intervalo.setFlags(item_intervalo.flags() & ~Qt.ItemFlag.ItemIsEditable)
            tabela.setItem(row, 0, item_intervalo)

            item_phi = QTableWidgetItem(f"{phi:.4f}")
            item_phi.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            item_phi.setFlags(item_phi.flags() & ~Qt.ItemFlag.ItemIsEditable)
            tabela.setItem(row, 1, item_phi)

        header = tabela.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        header.setStretchLastSection(True)

    def _inicializar_table_coef_manual(self):
        tabela = self.table_coef_manual
        tabela.clear()
        tabela.setColumnCount(3)
        tabela.setHorizontalHeaderLabels([
            "Início do Intervalo [m]",
            "Fim do Intervalo [m]",
            "Valor do Coeficiente",
        ])
        tabela.setRowCount(0)
        tabela.verticalHeader().setVisible(False)

        header = tabela.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        header.setStretchLastSection(True)

        self._adicionar_linha_manual(inicio=0.0, fim=self._L_total)

    def _adicionar_linha_manual(self, inicio: float, fim: float):
        tabela = self.table_coef_manual
        row    = tabela.rowCount()
        tabela.insertRow(row)

        item_inicio = QTableWidgetItem(f"{inicio:.3f}")
        item_inicio.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        item_inicio.setFlags(item_inicio.flags() & ~Qt.ItemFlag.ItemIsEditable)
        tabela.setItem(row, 0, item_inicio)

        spin_fim = QDoubleSpinBox()
        spin_fim.setDecimals(3)
        spin_fim.setSuffix(" m")
        spin_fim.setMinimum(round(inicio + 0.001, 3))
        spin_fim.setMaximum(round(self._L_total, 3))
        spin_fim.setSingleStep(0.5)
        spin_fim.setValue(round(min(fim, self._L_total), 3))
        spin_fim.valueChanged.connect(
            lambda valor, r=row: self._on_spin_fim_alterado(r, valor)
        )
        tabela.setCellWidget(row, 1, spin_fim)

        spin_phi = QDoubleSpinBox()
        spin_phi.setDecimals(3)
        spin_phi.setRange(1.0, 2.0)
        spin_phi.setSingleStep(0.001)
        spin_phi.setValue(1.300)
        spin_phi.valueChanged.connect(self._on_tabela_manual_alterada)
        tabela.setCellWidget(row, 2, spin_phi)

    def _on_spin_fim_alterado(self, row: int, novo_valor: float):
        if self._bloqueando_sinais_tabela:
            return

        self._bloqueando_sinais_tabela = True
        tabela = self.table_coef_manual

        while tabela.rowCount() > row + 1:
            tabela.removeRow(tabela.rowCount() - 1)

        if novo_valor < self._L_total - 1e-9:
            self._bloqueando_sinais_tabela = False
            self._adicionar_linha_manual(inicio=novo_valor, fim=self._L_total)
        else:
            self._bloqueando_sinais_tabela = False

        self._on_tabela_manual_alterada()

    def _on_tabela_manual_alterada(self):
        if self._bloqueando_sinais_tabela:
            return
        self._atualizar_dict_coef()

    def _construir_dict_coef_manual(self) -> dict:
        tabela    = self.table_coef_manual
        resultado = {}

        for row in range(tabela.rowCount()):
            item_inicio = tabela.item(row, 0)
            spin_fim    = tabela.cellWidget(row, 1)
            spin_phi    = tabela.cellWidget(row, 2)

            if item_inicio is None or spin_fim is None or spin_phi is None:
                continue

            try:
                x_ini = float(item_inicio.text().strip())
                x_fim = float(spin_fim.value())
                phi   = float(spin_phi.value())
                resultado[(round(x_ini, 6), round(x_fim, 6))] = phi
            except (ValueError, AttributeError):
                continue

        return resultado

    def _aplicar_estado_grupo_coef(self):
        automatico = self.coef_automatico.isChecked()

        self.table_coef.setEnabled(automatico)
        self.table_coef_manual.setEnabled(not automatico)

        if not automatico and self.table_coef_manual.rowCount() == 0:
            self._inicializar_table_coef_manual()

    def _on_coef_radio_alterado(self):
        self._aplicar_estado_grupo_coef()
        self._atualizar_dict_coef()

    def _atualizar_dict_coef(self):
        if self.coef_automatico.isChecked():
            zonas = getattr(self._coef_impacto, "zonas_impacto", {}) if self._coef_impacto else {}
            self._dict_coef = dict(zonas)
        else:
            self._dict_coef = self._construir_dict_coef_manual()

    def _renderizar_figura_coef(self):
        if self._fig_coef is not None:
            self._fig_coef.clear()
            plt.close(self._fig_coef)
            self._fig_coef = None

        while self._layout_desenho.count():
            item = self._layout_desenho.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()

        if not self._superestrutura or not self._dict_coef:
            placeholder = QLabel("Aguardando dados do coeficiente de impacto...")
            placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self._layout_desenho.addWidget(placeholder)
            return

        try:
            self._fig_coef = desenhar_figura_coeficiente(
                superestrutura=self._superestrutura,
                coeficientes=self._dict_coef,
                tipo_coeficiente="impacto",
            )
            self._layout_desenho.addWidget(FigureCanvas(self._fig_coef))
        except Exception as err:
            lbl = QLabel(f"Erro ao gerar figura do coeficiente:\n{err}")
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self._layout_desenho.addWidget(lbl)

    # -------------------------------------------------------------------------
    # Gerenciamento do Trem-Tipo
    # -------------------------------------------------------------------------
    def _preencher_combo_longarina(self):
        self.combo_longarina.blockSignals(True)
        self.combo_longarina.clear()

        if self._trem_longarina and hasattr(self._trem_longarina, "resumo_resultados"):
            chaves = list(self._trem_longarina.resumo_resultados.keys())
            self.combo_longarina.addItems([str(c) for c in chaves])

        self.combo_longarina.blockSignals(False)

    def _aplicar_estado_grupo_trem(self):
        carga = self.trem_carga.isChecked()

        self.combo_longarina.setEnabled(self.trem_longarina.isChecked())
        self.spin_q.setEnabled(carga)
        self.spin_q1.setEnabled(carga)
        self.spin_q2.setEnabled(carga)

        self._atualizar_labels_html_cargas(ativo=carga)

    def _atualizar_labels_html_cargas(self, ativo: bool):
        try:
            htmls = html_definir_cargas(ativo=ativo)
            self.html_q.setText(htmls.get("html_q",  ""))
            self.html_q1.setText(htmls.get("html_q1", ""))
            self.html_q2.setText(htmls.get("html_q2", ""))
        except Exception:
            pass

    def _on_trem_radio_alterado(self):
        self._aplicar_estado_grupo_trem()
        self._atualizar_dict_trem_tipo()

    def _on_combo_longarina_alterado(self, _texto: str):
        if self.trem_longarina.isChecked():
            self._atualizar_dict_trem_tipo()

    def _on_spin_trem_alterado(self, _valor):
        if self.trem_carga.isChecked():
            self._atualizar_dict_trem_tipo()

    def _atualizar_dict_trem_tipo(self):
        if self.trem_critico.isChecked():
            caso = getattr(self._trem_longarina, "caso_critico", {}) if self._trem_longarina else {}
            self._trem_tipo = {
                "Q":  float(caso.get("Q",  0.0)),
                "q1": float(caso.get("q1", 0.0)),
                "q2": float(caso.get("q2", 0.0)),
            }

        elif self.trem_longarina.isChecked():
            chave = self.combo_longarina.currentText()
            resumo = getattr(self._trem_longarina, "resumo_resultados", {}) if self._trem_longarina else {}
            dados  = resumo.get(chave, {})
            self._trem_tipo = {
                "Q":  float(dados.get("Q",  0.0)),
                "q1": float(dados.get("q1", 0.0)),
                "q2": float(dados.get("q2", 0.0)),
            }

        else:
            self._trem_tipo = {
                "Q":  self.spin_q.value(),
                "q1": self.spin_q1.value(),
                "q2": self.spin_q2.value(),
            }

        self._renderizar_html_trem_tipo()

    def _renderizar_html_trem_tipo(self):
        try:
            Q  = self._trem_tipo.get("Q",  0.0)
            q1 = self._trem_tipo.get("q1", 0.0)
            q2 = self._trem_tipo.get("q2", 0.0)
            html = gerar_html_trem_tipo(Q=Q, q1=q1, q2=q2)
            self.html_trem_tipo.setText(html)
        except Exception:
            pass

    def _renderizar_figura_esquema(self):
        if self._fig_esquema is not None:
            self._fig_esquema.clear()
            plt.close(self._fig_esquema)
            self._fig_esquema = None

        while self._layout_desenho2.count():
            item = self._layout_desenho2.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()

        Q  = self._trem_tipo.get("Q",  0.0)
        q1 = self._trem_tipo.get("q1", 0.0)
        q2 = self._trem_tipo.get("q2", 0.0)

        if Q == 0.0 and q1 == 0.0 and q2 == 0.0:
            placeholder = QLabel("Aguardando definição do Trem-Tipo...")
            placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self._layout_desenho2.addWidget(placeholder)
            return

        try:
            self._fig_esquema = desenhar_esquema_cargas(Q1=Q, q1=q1, q2=q2)
            self._layout_desenho2.addWidget(FigureCanvas(self._fig_esquema))
        except Exception as err:
            lbl = QLabel(f"Erro ao gerar esquema de cargas:\n{err}")
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self._layout_desenho2.addWidget(lbl)

    def _exibir_placeholder_desenho(self):
        while self._layout_desenho.count():
            item = self._layout_desenho.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()
        lbl = QLabel("Aguardando a Geração do Desenho")
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._layout_desenho.addWidget(lbl)

    def _exibir_placeholder_desenho2(self):
        while self._layout_desenho2.count():
            item = self._layout_desenho2.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()
        lbl = QLabel("Aguardando a Geração do Desenho")
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._layout_desenho2.addWidget(lbl)

    def _on_atualizar_desenho(self):
        self._renderizar_figura_coef()

    def _on_atualizar_desenho2(self):
        self._renderizar_figura_esquema()

    # =========================================================================
    # EXTRAÇÃO DE SEÇÕES CRÍTICAS
    # =========================================================================
    def _extrair_secoes_criticas(self, tabela: list, tipo: str) -> dict:
        """
        Localiza as linhas de máximo e mínimo em uma tabela de resultados
        usando os nomes das colunas (suporta coluna 'Seção').
        """
        if len(tabela) < 2:
            return {}

        cabecalho = tabela[0]
        dados = tabela[1:]

        if tipo == "Reações":
            idx_nome = cabecalho.index("Apoio") if "Apoio" in cabecalho else 0
            idx_pos  = cabecalho.index("Posição [m]") if "Posição [m]" in cabecalho else 1
            idx_min  = cabecalho.index("φ·R_min [kN]") if "φ·R_min [kN]" in cabecalho else cabecalho.index("R_min [kN]")
            idx_max  = cabecalho.index("φ·R_max [kN]") if "φ·R_max [kN]" in cabecalho else cabecalho.index("R_max [kN]")
        elif tipo == "Cortante":
            idx_pos  = cabecalho.index("Posição [m]") if "Posição [m]" in cabecalho else 0
            idx_min  = cabecalho.index("φ·V_min [kN]") if "φ·V_min [kN]" in cabecalho else cabecalho.index("V_min [kN]")
            idx_max  = cabecalho.index("φ·V_max [kN]") if "φ·V_max [kN]" in cabecalho else cabecalho.index("V_max [kN]")
        elif tipo == "Momento":
            idx_pos  = cabecalho.index("Posição [m]") if "Posição [m]" in cabecalho else 0
            idx_min  = cabecalho.index("φ·M_min [kNm]") if "φ·M_min [kNm]" in cabecalho else cabecalho.index("M_min [kNm]")
            idx_max  = cabecalho.index("φ·M_max [kNm]") if "φ·M_max [kNm]" in cabecalho else cabecalho.index("M_max [kNm]")
        else:
            return {}

        if tipo == "Reações":
            linha_max = max(dados, key=lambda l: float(l[idx_max]))
            linha_min = min(dados, key=lambda l: float(l[idx_min]))
            label_max = f"Apoio {linha_max[idx_nome]} ({float(linha_max[idx_pos]):.2f} m)"
            label_min = f"Apoio {linha_min[idx_nome]} ({float(linha_min[idx_pos]):.2f} m)"
            vmin_max = float(linha_max[idx_min])
            vmax_max = float(linha_max[idx_max])
            vmin_min = float(linha_min[idx_min])
            vmax_min = float(linha_min[idx_max])
        else:
            linha_max = max(dados, key=lambda l: float(l[idx_max]))
            linha_min = min(dados, key=lambda l: float(l[idx_min]))
            label_max = f"({float(linha_max[idx_pos]):.2f} m)"
            label_min = f"({float(linha_min[idx_pos]):.2f} m)"
            vmin_max = float(linha_max[idx_min])
            vmax_max = float(linha_max[idx_max])
            vmin_min = float(linha_min[idx_min])
            vmax_min = float(linha_min[idx_max])

        return {
            "Máximo": (label_max, round(vmin_max, 4), round(vmax_max, 4)),
            "Mínimo": (label_min, round(vmin_min, 4), round(vmax_min, 4)),
        }

    # =========================================================================
    # FLUXO DE CÁLCULO COM DIÁLOGO DE PROGRESSO
    # =========================================================================
    def _processar_calculos(self):
        if not self._superestrutura or not self._secao_super:
            QMessageBox.warning(
                self,
                "Aviso",
                "Superestrutura e Seção Transversal precisam estar definidas.",
            )
            return

        Q = self._trem_tipo.get("Q", 0.0)
        if Q <= 0.0:
            QMessageBox.warning(
                self,
                "Aviso",
                "Defina um Trem-Tipo com carga concentrada Q > 0 antes de calcular.",
            )
            return

        # Limpa figuras de resultados anteriores
        if self._fig_cortante is not None:
            self._fig_cortante.clear()
            plt.close(self._fig_cortante)
            self._fig_cortante = None
        if self._fig_momento is not None:
            self._fig_momento.clear()
            plt.close(self._fig_momento)
            self._fig_momento = None

        self._dialogo = _DialogoProgresso(self)
        self._dialogo.modo_selecionado.connect(self._iniciar_worker)
        self._dialogo.exec()

    def _iniciar_worker(self, modo: str):
        modulo_E_padrao = 3000.0
        try:
            self._calculadora = CalculadoraCargaMovel(
                superestrutura=self._superestrutura,
                secao_superestrutura=self._secao_super,
                trem_tipo=self._trem_tipo,
                modulo_elasticidade=modulo_E_padrao,
                dict_coef=self._dict_coef if self._dict_coef else None,
                modo=modo
            )
        except Exception as err:
            self._dialogo.mostrar_erro(f"Não foi possível inicializar a calculadora:\n{err}")
            return

        self._worker = _WorkerCalculo(self._calculadora)
        self._worker.concluido.connect(self._on_calculo_concluido)
        self._worker.erro.connect(self._on_calculo_erro)
        self._worker.start()

    def _on_calculo_concluido(
        self,
        tabela_reacoes:  list,
        tabela_cortante: list,
        tabela_momento:  list,
        elapsed:         float,
    ) -> None:
        self._tabela_reacoes  = tabela_reacoes
        self._tabela_cortante = tabela_cortante
        self._tabela_momento  = tabela_momento

        self._fig_cortante = self._calculadora.plotar_envoltoria_cortante()
        self._fig_momento  = self._calculadora.plotar_envoltoria_momento()

        secoes_criticas = {
            "Cortante": self._extrair_secoes_criticas(tabela_cortante, "Cortante"),
            "Momento":  self._extrair_secoes_criticas(tabela_momento,  "Momento"),
            "Reações":  self._extrair_secoes_criticas(tabela_reacoes,  "Reações"),
        }

        html_resumo = gerar_html_resultados_esforcos_calculos(
            secoes_criticas=secoes_criticas,
            tipo_dado="movel"
        )
        self.html_resultados_esforcos.setHtml(html_resumo)

        r_max = secoes_criticas["Reações"]["Máximo"][2]
        v_min = secoes_criticas["Cortante"]["Mínimo"][1]
        v_max = secoes_criticas["Cortante"]["Máximo"][2]
        m_min = secoes_criticas["Momento"]["Mínimo"][1]
        m_max = secoes_criticas["Momento"]["Máximo"][2]

        self.valores_limites = {
            "r_max": r_max,
            "v_min": v_min,
            "v_max": v_max,
            "m_min": m_min,
            "m_max": m_max,
        }

        self.botao_cortante.setEnabled(True)
        self.botao_momento.setEnabled(True)
        self.botao_reacoes.setEnabled(True)

        n_secoes    = max(0, len(tabela_cortante) - 1)
        n_apoios    = max(0, len(tabela_reacoes)  - 1)
        L_total_m   = self._calculadora._L_total_mm / 1000.0
        tipo_str    = getattr(self._superestrutura, "tipo", "–")

        metricas = (
            f"<b>Tipo estrutural:</b> {tipo_str}<br>"
            f"<b>Modo Utilizado:</b> {self._calculadora._modo}<br>"
            f"<b>Comprimento total:</b> {L_total_m:.2f} m<br>"
            f"<b>Seções apresentadas:</b> {n_secoes}<br>"
            f"<b>Tempo de execução:</b> {elapsed:.2f} s"
        )

        if self._dialogo is not None:
            self._dialogo.mostrar_sucesso(metricas)

    def _on_calculo_erro(self, mensagem: str) -> None:
        if self._dialogo is not None:
            self._dialogo.mostrar_erro(
                f"Falha no cálculo de Carga Móvel:\n{mensagem}"
            )

    # =========================================================================
    # JANELAS DE RESULTADOS
    # =========================================================================
    def _abrir_janela_cortante(self):
        if not self._calculadora:
            return

        if self._fig_cortante is not None:
            self._fig_cortante.clear()
            plt.close(self._fig_cortante)
        self._fig_cortante = self._calculadora.plotar_envoltoria_cortante()

        v_min = self.valores_limites.get("v_min", 0.0)
        v_max = self.valores_limites.get("v_max", 0.0)

        janela = LogicaJanelaResultadosEnvoltoria(
            titulo_janela="Envoltória do Esforço Cortante: Carga Móvel",
            titulo_diagrama="Envoltória de Esforço Cortante",
            titulo_tabela="Tabela de Esforço Cortante (Mín / Máx)",
            dados_tabela=self._tabela_cortante,
            figura_matplotlib=self._fig_cortante,
            valores_destaque_min=[v_min],
            valores_destaque_max=[v_max],
        )
        janela.exec()

    def _abrir_janela_momento(self):
        if not self._calculadora:
            return

        if self._fig_momento is not None:
            self._fig_momento.clear()
            plt.close(self._fig_momento)
        self._fig_momento = self._calculadora.plotar_envoltoria_momento()

        m_min = self.valores_limites.get("m_min", 0.0)
        m_max = self.valores_limites.get("m_max", 0.0)

        janela = LogicaJanelaResultadosEnvoltoria(
            titulo_janela="Envoltória do Momento Fletor: Carga Móvel",
            titulo_diagrama="Envoltória de Momento Fletor",
            titulo_tabela="Tabela de Momento Fletor (Mín / Máx)",
            dados_tabela=self._tabela_momento,
            figura_matplotlib=self._fig_momento,
            valores_destaque_min=[m_min],
            valores_destaque_max=[m_max],
        )
        janela.exec()

    def _abrir_janela_reacoes(self):
        r_max = self.valores_limites.get("r_max", 0.0)

        janela = LogicaJanelaResultadosReacoesCargaMovel(
            titulo_janela="Reações de Apoio: Carga Móvel (Mín / Máx)",
            dados_tabela=self._tabela_reacoes,
            valores_destaque_max=[r_max],
        )
        janela.exec()

    def _acao_confirmar(self):
        if not self._tabela_cortante or not self._tabela_momento or not self._tabela_reacoes:
            QMessageBox.warning(
                self,
                "Aviso",
                "Realize o cálculo antes de confirmar.",
            )
            return

        self._gerenciador.definir_esforco(
            nome="carga_movel",
            cortante=self._tabela_cortante,
            momento=self._tabela_momento,
            reacoes=self._tabela_reacoes,
            valores_limites=self.valores_limites
        )
        self.accept()

    # =========================================================================
    # Manual do usuário
    # =========================================================================
    def abrir_manual(self):
        """
        Abre o manual do software no PDFViewer na seção de análise da carga móvel.

        Navega diretamente para a página 65 do manual (índice 64 em base 0,
        pois o PyMuPDF (fitz) indexa páginas a partir de zero).
        """
        pdf_path = resource_path(os.path.join("assets", "Manual Girder25 Dark.pdf"))
        viewer = PDFViewer(pdf_path, "Manual: ANÁLISE DA CARGA MÓVEL")
        viewer.display_page(64)   # página 65 do manual → índice 64
        viewer.exec()