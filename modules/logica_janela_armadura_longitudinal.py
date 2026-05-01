# ============================================================================
# Girder25 - logica_janela_armadura_longitudinal.py
# Autor: Fábio Henrique Sampaio Júnior
# Controlador do dimensionamento da armadura longitudinal.
# ============================================================================

import math
import os

import matplotlib
matplotlib.use('QtAgg')

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QMessageBox, QFileDialog, QButtonGroup, QLabel,
    QDoubleSpinBox,
)
from PyQt6.QtCore import Qt

from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
import matplotlib.pyplot as plt

from ui.janela_armadura_longitudinal import Ui_janela_armadura_longitudinal
from modules.logica_janela_memorial import LogicaJanelaMemorial
from modules.logica_janela_def_superestrutura import DialogoExportacao
from modules.exportar_dxf import exportar_figura_para_dxf
from modules.visualizador_pdf import PDFViewer
from modules.utils import resource_path

from modules.funcoes_janela_armadura_longitudinal import (
    gerar_html_d_estimado,
    gerar_html_resumo_primeira_iteracao,
    gerar_html_d_real,
    gerar_html_as_adotado,
    gerar_html_comparacao,
    calcular_relacao_modular,
    calcular_amplitude_tensao,
    obter_html_verificacao_fadiga,
    calcular_largura_colaborante,
    calcular_espacamento_minimo,
)
from modules.funcoes_sec_super import desenhar_secao
from modules.Calculadora_Flexao_Simples import CalculadoraFlexaoSimples
from modules.Calculadora_Flexao_Fadiga import CalculadoraFlexaoFadiga
from modules.detalhamento_armadura import desenhar_detalhamento
from modules.desenho_envelope import desenhar_envelope_calculo, ativar_interatividade_envelope


# Valor sentinela para os QDoubleSpinBox de d quando em modo "primeira iteração".
_SENTINEL_D = -1.0


class LogicaJanelaArmaduraLongitudinal(QDialog, Ui_janela_armadura_longitudinal):
    """
    Controlador do dimensionamento da armadura longitudinal.

    Gerencia: leitura de esforços, cálculo de armaduras, detalhamento,
    verificação de conformidade e fadiga.
    """

    def __init__(self, gerenciador, parent=None):
        super().__init__(parent)
        self.setupUi(self)
        self.setWindowTitle("Dimensionamento da Armadura Longitudinal")
        self.gerenciador = gerenciador

        # ── Dados da superestrutura ───────────────────────────────────────────
        self.esforcos_obj = self.gerenciador.get_esforcos_calculo()
        self.sup          = self.gerenciador.get_superestrutura()
        self.sec_super    = self.gerenciador.get_secao_superestrutura()

        if not self.esforcos_obj or not self.sup or not self.sec_super:
            QMessageBox.critical(
                self, "Erro",
                "Dados insuficientes para iniciar o dimensionamento.\n"
                "Certifique-se de que a superestrutura e os esforços foram calculados.",
            )
            self.reject()
            return

        # ── Estado interno ────────────────────────────────────────────────────
        self.fig_dcl            = None
        self.fig_laje           = None
        self.fig_detalhamento   = None

        self._d_inf_estimado: float = 0.0
        self._d_sup_estimado: float = 0.0

        self.bf_html_memorial       = ""
        self.ah_inf_html_memorial   = ""
        self.ah_sup_html_memorial   = ""
        self.n_eq_html_memorial     = ""
        self.delta_html_memorial    = ""

        self.calc_flexao_inf = None
        self.calc_flexao_sup = None
        self.calc_fadiga     = None

        self.As_calc_inferior  = None
        self.As_calc_superior  = None

        self.As_adotado_inferior  = 0.0
        self.As_adotado_superior  = 0.0

        self.d_prime_inf = 0.0
        self.d_prime_sup = 0.0

        # ── Inicialização ─────────────────────────────────────────────────────
        self._criar_grupos_botoes()
        self._configurar_ui_inicial()
        self._conectar_sinais()
        self._aplicar_estados_padrao()
        self._carregar_dados()
        self._ajustar_scroll_area()

    # -------------------------------------------------------------------------
    # Gerenciamento da janela
    # -------------------------------------------------------------------------
    def closeEvent(self, event):
        """Libera todas as figuras do Matplotlib ao fechar o diálogo."""
        for fig in (self.fig_dcl, self.fig_laje, self.fig_detalhamento):
            if fig:
                plt.close(fig)
        self.fig_dcl = None
        self.fig_laje = None
        self.fig_detalhamento = None
        super().closeEvent(event)

    # =========================================================================
    # INICIALIZAÇÃO
    # =========================================================================

    def _criar_grupos_botoes(self):
        """Cria QButtonGroup para cada conjunto de radiobuttons exclusivos."""
        self.grupo_estado_envelope = QButtonGroup(self)
        self.grupo_estado_envelope.addButton(self.radioELU)
        self.grupo_estado_envelope.addButton(self.radioELS)

        self.grupo_msd = QButtonGroup(self)
        self.grupo_msd.addButton(self.msd_automatico)
        self.grupo_msd.addButton(self.msd_manual)

        self.grupo_laje = QButtonGroup(self)
        self.grupo_laje.addButton(self.laje_automatico)
        self.grupo_laje.addButton(self.laje_manual)
        self.grupo_laje.addButton(self.laje_n_considerar)

        self.grupo_d_iteracao = QButtonGroup(self)
        self.grupo_d_iteracao.addButton(self.primeira_iteracao)
        self.grupo_d_iteracao.addButton(self.reiteracao)

        self.grupo_as_inf = QButtonGroup(self)
        self.grupo_as_inf.addButton(self.as_inf_automatico)
        self.grupo_as_inf.addButton(self.as_inf_manual)

        self.grupo_as_sup = QButtonGroup(self)
        self.grupo_as_sup.addButton(self.as_sup_automatico)
        self.grupo_as_sup.addButton(self.as_sup_manual)

        self.grupo_a_inf = QButtonGroup(self)
        self.grupo_a_inf.addButton(self.a_inf_automatico)
        self.grupo_a_inf.addButton(self.a_inf_manual)

        self.grupo_a_sup = QButtonGroup(self)
        self.grupo_a_sup.addButton(self.a_sup_automatico)
        self.grupo_a_sup.addButton(self.a_sup_manual)

        self.grupo_d_real = QButtonGroup(self)
        self.grupo_d_real.addButton(self.d_automatico)
        self.grupo_d_real.addButton(self.d_manual)

        self.grupo_n_eq = QButtonGroup(self)
        self.grupo_n_eq.addButton(self.n_automatico)
        self.grupo_n_eq.addButton(self.n_manual)

        self.grupo_delta_fad = QButtonGroup(self)
        self.grupo_delta_fad.addButton(self.delta_fad_automatico)
        self.grupo_delta_fad.addButton(self.delta_fad_manual)

    def _aplicar_estados_padrao(self):
        """Marca os radiobuttons padrão sem disparar lógica."""
        self.radioELU.setChecked(True)

        self.msd_automatico.setChecked(True)
        self.laje_automatico.setChecked(True)
        self.primeira_iteracao.setChecked(True)
        self.as_inf_automatico.setChecked(True)
        self.as_sup_automatico.setChecked(True)
        self.a_inf_automatico.setChecked(True)
        self.a_sup_automatico.setChecked(True)
        self.d_automatico.setChecked(True)
        self.n_automatico.setChecked(True)
        self.delta_fad_automatico.setChecked(True)

    def _configurar_ui_inicial(self):
        """Configura layouts, sufixos, ranges e textos iniciais."""
        # Layouts dos QFrames de desenho
        self.layout_dcl = QVBoxLayout(self.desenho_dlc_secao)
        self.layout_dcl.setContentsMargins(0, 0, 0, 0)
        self._exibir_texto_qframe(self.layout_dcl, "Aguardando Cálculo dos Esforços")

        self.layout_laje = QVBoxLayout(self.frame_desenho_laje)
        self.layout_laje.setContentsMargins(0, 0, 0, 0)
        self._exibir_texto_qframe(self.layout_laje, "Aguardando Geração do Desenho")

        self.layout_detalhamento = QVBoxLayout(self.deseneho_detalhamento)
        self.layout_detalhamento.setContentsMargins(0, 0, 0, 0)
        self._exibir_texto_qframe(self.layout_detalhamento, "Aguardando Geração do Desenho")

        # Sufixos de unidade
        for spin in [self.m_max_elu, self.m_min_elu, self.m_max_els, self.m_min_els]:
            spin.setSuffix(" kN·m")
        for spin in [self.doubleSpin_bf, self.doubleSpinBox_d_inf,
                     self.doubleSpinBox_d_sup, self.doubleSpinBox_d_real_inf,
                     self.doubleSpinBox_d_real_sup]:
            spin.setSuffix(" cm")
        for spin in [self.doubleSpinBox_c, self.doubleSpinBox_folga_vibrador,
                     self.doubleSpinBox_d_max_agregado, self.doubleSpinBox_ah_min_inf,
                     self.doubleSpinBox_av_inf, self.doubleSpinBox_ah_min_sup,
                     self.doubleSpinBox_av_sup]:
            spin.setSuffix(" mm")
        for spin in [self.doubleSpinBox_as_inf, self.doubleSpinBox_as_sup]:
            spin.setSuffix(" cm²")
        self.doubleSpinBox_n_eq.setSuffix("")
        self.doubleSpinBox_delta_sup.setSuffix(" MPa")
        self.doubleSpinBox_delta_inf.setSuffix(" MPa")

        # Faixas iniciais
        self.doubleSpinBox_c.setRange(25.0, 60.0)
        self.doubleSpinBox_c.setValue(40.0)
        self.doubleSpinBox_folga_vibrador.setRange(20.0, 100.0)
        self.doubleSpinBox_folga_vibrador.setValue(60.0)
        self.doubleSpinBox_d_max_agregado.setRange(9.5, 50.0)
        self.doubleSpinBox_d_max_agregado.setValue(19.0)
        self.doubleSpinBox_n_eq.setRange(4.0, 12.0)
        self.doubleSpinBox_delta_sup.setRange(150.0, 190.0)
        self.doubleSpinBox_delta_inf.setRange(150.0, 190.0)

        # Spinboxes de d (primeira iteração)
        for spin in (self.doubleSpinBox_d_inf, self.doubleSpinBox_d_sup):
            spin.setSpecialValueText("—")
            spin.setRange(_SENTINEL_D, 999.0)
            spin.setValue(_SENTINEL_D)
            spin.setReadOnly(True)

        # Textos iniciais
        self.label_resultado_inferior.setText("Cálculos ainda não realizados.")
        self.label_resultado_superior.setText("Cálculos ainda não realizados.")
        self.label_as_adotado_inf.setText(
            "Ainda não foi realizado o posicionamento da armadura.")
        self.label_as_adotado_sup.setText(
            "Ainda não foi realizado o posicionamento da armadura.")
        self.label_d_calculado_inf.setText("")
        self.label_d_calculado_sup.setText("")
        self.label_analise_conformidade.setText(
            "Aguardando cálculos da área de aço e posicionamento da armadura.")
        self.html_verificao_fadiga.setText(
            "A verificação à fadiga ainda não foi realizada.")

        # Desabilita botões condicionais
        self.memorial_armadura_positiva.setEnabled(False)
        self.memorial_armadura_negativa.setEnabled(False)
        self.exportar_deseneho_detalhamento.setEnabled(False)
        self.exportar_frame_desenho_laje.setEnabled(False)
        self.memorial_fadiga.setEnabled(False)

        self.combo_estribo.setCurrentText("ø 12.5 mm")

        self._aplicar_estilo_readonly()

    def _exibir_texto_qframe(self, layout, texto):
        """Remove widgets do layout e exibe um QLabel centralizado."""
        for i in reversed(range(layout.count())):
            widget = layout.itemAt(i).widget()
            if widget:
                widget.setParent(None)
        label = QLabel(texto)
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(label)

    def _aplicar_estilo_readonly(self):
        self._update_readonly_style()

    def _update_readonly_style(self):
        """Aplica fundo escuro e texto claro em spinboxes somente leitura."""
        ro_style = """
            QDoubleSpinBox[readOnly="true"] {
                background-color: #2d2d2d;
                color: #ffffff;
                border: 1px solid #555;
            }
        """
        for spin in self.findChildren(QDoubleSpinBox):
            spin.setStyleSheet(ro_style if spin.isReadOnly() else "")

    def _conectar_sinais(self):
        """Conecta todos os sinais de widgets aos seus slots."""
        self.radioELU.clicked.connect(self._atualizar_envelope)
        self.radioELS.clicked.connect(self._atualizar_envelope)

        self.combo_secao.currentIndexChanged.connect(self._atualizar_secao_selecionada)

        self.msd_automatico.toggled.connect(self._toggle_msd)
        self.msd_manual.toggled.connect(self._toggle_msd)

        self.laje_automatico.toggled.connect(self._toggle_laje)
        self.laje_manual.toggled.connect(self._toggle_laje)
        self.laje_n_considerar.toggled.connect(self._toggle_laje)
        self.combo_posicao_longarina.currentIndexChanged.connect(
            self._recalcular_laje_colaborante)

        self.memorial_bf.clicked.connect(
            lambda: self._abrir_memorial(
                "Memorial de Cálculo Laje: Largura Colaborante (bf)",
                self.bf_html_memorial))
        self.atualizar_desenho_laje.clicked.connect(self._atualizar_desenho_laje)
        self.exportar_frame_desenho_laje.clicked.connect(
            lambda: self._exportar_grafico(self.fig_laje))
        self.exportar_desenho_dlc_secao.clicked.connect(
            lambda: self._exportar_grafico(self.fig_dcl))

        self.primeira_iteracao.toggled.connect(self._toggle_iteracao)
        self.reiteracao.toggled.connect(self._toggle_iteracao)
        self.calcular_armadura.clicked.connect(self._calcular_armadura_longitudinal)

        self.memorial_armadura_positiva.clicked.connect(self._abrir_memorial_flexao_inf)
        self.memorial_armadura_negativa.clicked.connect(self._abrir_memorial_flexao_sup)

        self.as_inf_automatico.toggled.connect(self._toggle_as_inf)
        self.as_inf_manual.toggled.connect(self._toggle_as_inf)
        self.as_sup_automatico.toggled.connect(self._toggle_as_sup)
        self.as_sup_manual.toggled.connect(self._toggle_as_sup)

        self.a_inf_automatico.toggled.connect(self._toggle_a_inf)
        self.a_inf_manual.toggled.connect(self._toggle_a_inf)
        self.a_sup_automatico.toggled.connect(self._toggle_a_sup)
        self.a_sup_manual.toggled.connect(self._toggle_a_sup)

        self.d_automatico.toggled.connect(self._toggle_d_real)
        self.d_manual.toggled.connect(self._toggle_d_real)

        self.combo_diametro_as_inf.currentIndexChanged.connect(self._recalcular_espacamentos)
        self.combo_diametro_as_sup.currentIndexChanged.connect(self._recalcular_espacamentos)
        self.doubleSpinBox_d_max_agregado.valueChanged.connect(self._recalcular_espacamentos)

        self.memorial_a_inf.clicked.connect(
            lambda: self._abrir_memorial("Memorial Espaçamento Inf",
                                          self.ah_inf_html_memorial))
        self.memorial_a_sup.clicked.connect(
            lambda: self._abrir_memorial("Memorial Espaçamento Sup",
                                          self.ah_sup_html_memorial))

        self.posicionar_e_calcular.clicked.connect(self._posicionar_e_calcular)
        self.exportar_deseneho_detalhamento.clicked.connect(
            lambda: self._exportar_grafico(self.fig_detalhamento))

        self.analisar_conformidade.clicked.connect(self._analisar_conformidade)

        self.n_automatico.toggled.connect(self._toggle_n_fadiga)
        self.n_manual.toggled.connect(self._toggle_n_fadiga)
        self.combo_classe_concreto.currentIndexChanged.connect(self._recalcular_n_fadiga)
        self.combo_tipo_agregado.currentIndexChanged.connect(self._recalcular_n_fadiga)
        self.memorial_n_eq.clicked.connect(
            lambda: self._abrir_memorial("Memorial Relação Modular",
                                          self.n_eq_html_memorial))

        self.delta_fad_automatico.toggled.connect(self._toggle_delta_fadiga)
        self.delta_fad_manual.toggled.connect(self._toggle_delta_fadiga)
        self.memorial_delta.clicked.connect(
            lambda: self._abrir_memorial("Memorial Amplitude de Tensão",
                                          self.delta_html_memorial))

        self.vereficiar_fadiga.clicked.connect(self._verificar_fadiga)
        self.memorial_fadiga.clicked.connect(self._abrir_memorial_fadiga_completo)

        # Manual do usuário
        self.manual.clicked.connect(self.abrir_manual)

        self.cancelar.clicked.connect(self.reject)
        self.confirmar.clicked.connect(self.accept)

    def _ajustar_scroll_area(self):
        """Expande a área de rolagem se o conteúdo for maior que o visível."""
        last_widget = self.groupBox_verficacao_fadiga
        if last_widget:
            total_height = last_widget.geometry().bottom() + 30
            current_geo  = self.scrollAreaWidgetContents.geometry()
            if total_height > current_geo.height():
                self.scrollAreaWidgetContents.setGeometry(
                    current_geo.x(), current_geo.y(),
                    current_geo.width(), total_height,
                )

    def _carregar_dados(self):
        """Popula o combo de seções e desenha o envelope de momento (ELU)."""
        if not self.esforcos_obj or not self.esforcos_obj.resultados:
            return
        tabela_elu = self.esforcos_obj.resultados["ELU"]["Momento"]
        self.combo_secao.clear()
        for row in tabela_elu[1:]:
            pos  = row[0]
            nome = row[1]
            self.combo_secao.addItem(str(nome), userData={"nome": nome, "pos": pos})
        self._atualizar_envelope()

    # =========================================================================
    # GroupBox 1: Envelope de Momento e Esforços por Seção
    # =========================================================================

    def _atualizar_envelope(self):
        """Exibe o envelope de momento (ELU ou ELS) com interatividade."""
        if not self.esforcos_obj or not getattr(self.esforcos_obj, 'resultados', None):
            self._exibir_texto_qframe(self.layout_dcl, "Aguardando Cálculo dos Esforços")
            return

        estado = "ELU" if self.radioELU.isChecked() else "ELS"

        if self.fig_dcl:
            plt.close(self.fig_dcl)
            self.fig_dcl = None
        for i in reversed(range(self.layout_dcl.count())):
            widget = self.layout_dcl.itemAt(i).widget()
            if widget:
                widget.setParent(None)

        try:
            self.fig_dcl = desenhar_envelope_calculo(
                esforcos_calculo=self.esforcos_obj,
                esforco="momento",
                combinacao=estado,
            )
        except Exception as e:
            self._exibir_texto_qframe(
                self.layout_dcl, f"Erro ao gerar envelope:\n{str(e)}")
            return

        canvas = FigureCanvas(self.fig_dcl)
        ativar_interatividade_envelope(self.fig_dcl, canvas)
        self.layout_dcl.addWidget(canvas)

    def _atualizar_secao_selecionada(self):
        """
        Preenche os esforços solicitantes para a seção selecionada
        e recalcula a laje colaborante.
        """
        idx = self.combo_secao.currentIndex()
        if idx < 0:
            return
        dados_sec = self.combo_secao.itemData(idx)
        if not dados_sec:
            return

        nome = dados_sec["nome"]

        if self.msd_automatico.isChecked():
            for row in self.esforcos_obj.resultados["ELU"]["Momento"][1:]:
                if row[1] == nome:
                    self.m_max_elu.setValue(float(row[2]))
                    self.m_min_elu.setValue(float(row[3]))
                    break
            for row in self.esforcos_obj.resultados["ELS"]["Momento"][1:]:
                if row[1] == nome:
                    self.m_max_els.setValue(float(row[2]))
                    self.m_min_els.setValue(float(row[3]))
                    break

        self._recalcular_laje_colaborante()

    def _toggle_msd(self):
        """Alterna esforços solicitantes entre modo automático e manual."""
        is_auto = self.msd_automatico.isChecked()
        for spin in [self.m_max_elu, self.m_min_elu, self.m_max_els, self.m_min_els]:
            spin.setReadOnly(is_auto)
            spin.setMinimum(-999999.0)
            spin.setMaximum(+999999.0)

        self._update_readonly_style()
        if is_auto:
            self._atualizar_secao_selecionada()

    def _toggle_laje(self):
        """Alterna entre modo automático, manual e 'não considerar' para a laje."""
        if self.laje_automatico.isChecked():
            self.doubleSpin_bf.setReadOnly(True)
            self.combo_posicao_longarina.setEnabled(True)
            self.memorial_bf.setEnabled(True)
            self._recalcular_laje_colaborante()
        elif self.laje_manual.isChecked():
            self.doubleSpin_bf.setReadOnly(False)
            self.doubleSpin_bf.setMinimum(0.01)
            self.doubleSpin_bf.setMaximum(99999.0)
            self.combo_posicao_longarina.setEnabled(False)
            self.memorial_bf.setEnabled(False)
        elif self.laje_n_considerar.isChecked():
            self.doubleSpin_bf.setReadOnly(True)
            self.doubleSpin_bf.setValue(0.0)
            self.combo_posicao_longarina.setEnabled(False)
            self.memorial_bf.setEnabled(False)

        self._update_readonly_style()
        self._atualizar_d_estimado()

    def _recalcular_laje_colaborante(self):
        """Recalcula automaticamente a largura colaborante (bf)."""
        if not self.laje_automatico.isChecked():
            return
        if self.combo_secao.currentIndex() < 0:
            return

        pos_val   = self.combo_secao.itemData(self.combo_secao.currentIndex())["pos"]
        x_val     = float(pos_val)
        tipo_viga = ("centro"
                     if self.combo_posicao_longarina.currentText() == "Centro"
                     else "extremidade")

        try:
            mem_str, mem_html, bf_val = calcular_largura_colaborante(
                self.sup, self.sec_super, x_val, tipo_viga)
            self.doubleSpin_bf.setRange(0, 99999.0)
            self.doubleSpin_bf.setValue(bf_val * 100.0)
            self.bf_html_memorial = mem_html
        except Exception as e:
            self.doubleSpin_bf.setValue(0.0)
            self.bf_html_memorial = f"Erro no cálculo: {str(e)}"
            QMessageBox.warning(self, "Erro",
                                f"Não foi possível calcular a largura colaborante:\n{e}")

        self._atualizar_d_estimado()

    def _atualizar_desenho_laje(self):
        """Exibe o desenho da seção com a laje colaborante."""
        if self.fig_laje:
            plt.close(self.fig_laje)
            self.fig_laje = None
        for i in reversed(range(self.layout_laje.count())):
            widget = self.layout_laje.itemAt(i).widget()
            if widget:
                widget.setParent(None)

        bf_cm  = self.doubleSpin_bf.value()
        h_laje = self.sec_super.h_laje
        dados  = self.sec_super.dados.copy()

        if bf_cm > 0:
            self.fig_laje = desenhar_secao(dados, exibir_cotas=True,
                                           h_laje=h_laje,
                                           largura_colaborante=bf_cm)
        else:
            self.fig_laje = desenhar_secao(dados, exibir_cotas=True,
                                           h_laje=None, largura_colaborante=None)

        self.layout_laje.addWidget(FigureCanvas(self.fig_laje))
        self.exportar_frame_desenho_laje.setEnabled(True)

    # =========================================================================
    # GroupBox 2: Parâmetros de Cálculo
    # =========================================================================

    def _toggle_iteracao(self):
        """
        Alterna entre primeira iteração (d estimado) e reiteração (d manual).
        """
        is_primeira = self.primeira_iteracao.isChecked()
        h_total     = self._get_h_total()

        self._atualizar_d_estimado()

        if is_primeira:
            for spin in (self.doubleSpinBox_d_inf, self.doubleSpinBox_d_sup):
                spin.setReadOnly(True)
                spin.setSpecialValueText("—")
                spin.setRange(_SENTINEL_D, h_total)
                spin.setValue(_SENTINEL_D)
        else:
            d_inf_inicial = (self._d_inf_estimado if self._d_inf_estimado > 0
                             else h_total * 0.90)
            d_sup_inicial = (self._d_sup_estimado if self._d_sup_estimado > 0
                             else h_total * 0.85)
            for spin in (self.doubleSpinBox_d_inf, self.doubleSpinBox_d_sup):
                spin.setSpecialValueText("")
                spin.setRange(0.1, h_total)
                spin.setReadOnly(False)
            self.doubleSpinBox_d_inf.setValue(d_inf_inicial)
            self.doubleSpinBox_d_sup.setValue(d_sup_inicial)

        self._update_readonly_style()

    def _get_h_total(self) -> float:
        """Altura total da seção (longarina + laje)."""
        h_long = self.sec_super.dados.get("h", 0)
        h_laje = self.sec_super.h_laje if self.doubleSpin_bf.value() > 0 else 0
        return h_long + h_laje

    def _atualizar_d_estimado(self):
        """Recalcula d estimado e atualiza o memorial."""
        h_total = self._get_h_total()
        d_inf, d_sup, html = gerar_html_d_estimado(h_total)
        self.label_altura_estimada.setText(html)
        self._d_inf_estimado = d_inf
        self._d_sup_estimado = d_sup

    def _get_d_dimensionamento(self) -> tuple[float, float]:
        """
        Retorna (d_inf, d_sup) conforme o modo de iteração:
        primeira iteração → valores estimados; reiteração → spinboxes.
        """
        if self.primeira_iteracao.isChecked():
            return self._d_inf_estimado, self._d_sup_estimado
        return self.doubleSpinBox_d_inf.value(), self.doubleSpinBox_d_sup.value()

    def _calcular_armadura_longitudinal(self):
        """
        Dimensiona armadura inferior (se m_max > 0) e superior (se m_min < 0).
        Utiliza instâncias independentes da calculadora.
        """
        dados_secao = self.sec_super.dados.copy()
        m_max = self.m_max_elu.value()
        m_min = self.m_min_elu.value()
        d_pos, d_neg = self._get_d_dimensionamento()

        fck = float(self.combo_classe_concreto.currentText().replace("C", ""))
        fyk = 500.0

        bf     = self.doubleSpin_bf.value()
        h_laje = self.sec_super.h_laje if bf > 0 else None
        b_laje = bf if bf > 0 else None

        self.calc_flexao_inf  = None
        self.calc_flexao_sup  = None
        self.As_calc_inferior = None
        self.As_calc_superior = None

        calc_inf = CalculadoraFlexaoSimples()
        calc_sup = CalculadoraFlexaoSimples()

        # Armadura inferior (m_max > 0)
        if m_max > 0:
            try:
                res = calc_inf.dimensionar(
                    dados=dados_secao, Msd=m_max, d_pos=d_pos, d_neg=d_neg,
                    fck=fck, fyk=fyk, h_laje=h_laje, b_laje=b_laje,
                )
                self.calc_flexao_inf  = calc_inf
                self.As_calc_inferior = res.As_adotar
                self.label_resultado_inferior.setText(
                    gerar_html_resumo_primeira_iteracao(res))
                self.memorial_armadura_positiva.setEnabled(True)
            except Exception as e:
                self.As_calc_inferior = None
                self.label_resultado_inferior.setText(
                    f"Erro no dimensionamento inferior: {e}")
                self.memorial_armadura_positiva.setEnabled(False)
        else:
            self.As_calc_inferior = None
            self.label_resultado_inferior.setText(
                "Não foi calculada armadura longitudinal inferior pois o momento "
                f"máximo de cálculo ({m_max:.2f} kN·m) não é positivo. Fibras "
                "inferiores não são tracionadas nesta seção."
            )
            self.memorial_armadura_positiva.setEnabled(False)

        # Armadura superior (m_min < 0)
        if m_min < 0:
            try:
                res = calc_sup.dimensionar(
                    dados=dados_secao, Msd=m_min, d_pos=d_pos, d_neg=d_neg,
                    fck=fck, fyk=fyk, h_laje=h_laje, b_laje=b_laje,
                )
                self.calc_flexao_sup  = calc_sup
                self.As_calc_superior = res.As_adotar
                self.label_resultado_superior.setText(
                    gerar_html_resumo_primeira_iteracao(res))
                self.memorial_armadura_negativa.setEnabled(True)
            except Exception as e:
                self.As_calc_superior = None
                self.label_resultado_superior.setText(
                    f"Erro no dimensionamento superior: {e}")
                self.memorial_armadura_negativa.setEnabled(False)
        else:
            self.As_calc_superior = None
            self.label_resultado_superior.setText(
                "Não foi calculada armadura longitudinal superior pois o momento "
                f"mínimo de cálculo ({m_min:.2f} kN·m) não é negativo. Fibras "
                "superiores não são tracionadas nesta seção."
            )
            self.memorial_armadura_negativa.setEnabled(False)

        self._toggle_as_inf()
        self._toggle_as_sup()

    def _abrir_memorial_flexao_inf(self):
        """Memorial da armadura inferior (positiva)."""
        if not self.calc_flexao_inf:
            return
        _, html = self.calc_flexao_inf.obter_relatorio_resumido()
        self._abrir_memorial("Memorial de Cálculo Armadura Positiva (Inferior)", html)

    def _abrir_memorial_flexao_sup(self):
        """Memorial da armadura superior (negativa)."""
        if not self.calc_flexao_sup:
            return
        _, html = self.calc_flexao_sup.obter_relatorio_resumido()
        self._abrir_memorial("Memorial de Cálculo Armadura Negativa (Superior)", html)

    # =========================================================================
    # GroupBox 4: Detalhamento
    # =========================================================================

    def _toggle_as_inf(self):
        """Área de aço inferior: automático (calculado) ou manual."""
        is_auto = self.as_inf_automatico.isChecked()
        self.doubleSpinBox_as_inf.setReadOnly(is_auto)
        if is_auto and self.As_calc_inferior is not None:
            self.doubleSpinBox_as_inf.setRange(0, 9999.0)
            self.doubleSpinBox_as_inf.setValue(self.As_calc_inferior)
        elif is_auto:
            self.doubleSpinBox_as_inf.setValue(0.0)
        self._update_readonly_style()

    def _toggle_as_sup(self):
        """Área de aço superior: automático (calculado) ou manual."""
        is_auto = self.as_sup_automatico.isChecked()
        self.doubleSpinBox_as_sup.setReadOnly(is_auto)
        if is_auto and self.As_calc_superior is not None:
            self.doubleSpinBox_as_sup.setRange(0, 9999.0)
            self.doubleSpinBox_as_sup.setValue(self.As_calc_superior)
        elif is_auto:
            self.doubleSpinBox_as_sup.setValue(0.0)
        self._update_readonly_style()

    def _recalcular_espacamentos(self):
        self._toggle_a_inf()
        self._toggle_a_sup()

    def _toggle_a_inf(self):
        """Espaçamentos inferiores: automático (calculado) ou manual."""
        is_auto = self.a_inf_automatico.isChecked()
        self.doubleSpinBox_ah_min_inf.setReadOnly(is_auto)
        self.doubleSpinBox_av_inf.setReadOnly(is_auto)
        self.memorial_a_inf.setEnabled(is_auto)

        if is_auto:
            d_bar = float(
                self.combo_diametro_as_inf.currentText()
                .replace("ø ", "").replace(" mm", ""))
            d_ag  = self.doubleSpinBox_d_max_agregado.value()
            ah, av, html = calcular_espacamento_minimo(d_bar, d_ag)
            self.doubleSpinBox_ah_min_inf.setRange(0, 999.0)
            self.doubleSpinBox_av_inf.setRange(0, 999.0)
            self.doubleSpinBox_ah_min_inf.setValue(ah)
            self.doubleSpinBox_av_inf.setValue(av)
            self.ah_inf_html_memorial = html
        self._update_readonly_style()

    def _toggle_a_sup(self):
        """Espaçamentos superiores: automático (calculado) ou manual."""
        is_auto = self.a_sup_automatico.isChecked()
        self.doubleSpinBox_ah_min_sup.setReadOnly(is_auto)
        self.doubleSpinBox_av_sup.setReadOnly(is_auto)
        self.memorial_a_sup.setEnabled(is_auto)

        if is_auto:
            d_bar = float(
                self.combo_diametro_as_sup.currentText()
                .replace("ø ", "").replace(" mm", ""))
            d_ag  = self.doubleSpinBox_d_max_agregado.value()
            ah, av, html = calcular_espacamento_minimo(d_bar, d_ag)
            self.doubleSpinBox_ah_min_sup.setRange(0, 999.0)
            self.doubleSpinBox_av_sup.setRange(0, 999.0)
            self.doubleSpinBox_ah_min_sup.setValue(ah)
            self.doubleSpinBox_av_sup.setValue(av)
            self.ah_sup_html_memorial = html
        self._update_readonly_style()

    def _posicionar_e_calcular(self):
        """
        Posiciona as armaduras na seção, gera o detalhamento e calcula d'.
        """
        dados = self.sec_super.dados.copy()

        c           = self.doubleSpinBox_c.value() / 10.0
        folga_vib   = self.doubleSpinBox_folga_vibrador.value() / 10.0
        phi_estribo = float(
            self.combo_estribo.currentText().replace("ø ", "").replace(" mm", ""))

        # Armadura inferior
        as_inf_req   = self.doubleSpinBox_as_inf.value()
        phi_inf_mm   = float(
            self.combo_diametro_as_inf.currentText().replace("ø ", "").replace(" mm", ""))
        area_bar_inf = math.pi * (phi_inf_mm / 10.0) ** 2 / 4.0
        n_inf        = math.ceil(as_inf_req / area_bar_inf) if as_inf_req > 0 else 0
        self.As_adotado_inferior = n_inf * area_bar_inf
        dict_inf     = {"n": n_inf, "diametro": phi_inf_mm} if n_inf > 0 else None

        # Armadura superior
        as_sup_req   = self.doubleSpinBox_as_sup.value()
        phi_sup_mm   = float(
            self.combo_diametro_as_sup.currentText().replace("ø ", "").replace(" mm", ""))
        area_bar_sup = math.pi * (phi_sup_mm / 10.0) ** 2 / 4.0
        n_sup        = math.ceil(as_sup_req / area_bar_sup) if as_sup_req > 0 else 0
        self.As_adotado_superior = n_sup * area_bar_sup
        dict_sup     = {"n": n_sup, "diametro": phi_sup_mm} if n_sup > 0 else None

        bf     = self.doubleSpin_bf.value()
        h_laje = self.sec_super.h_laje if bf > 0 else None
        b_laje = bf if bf > 0 else None

        ah_inf = self.doubleSpinBox_ah_min_inf.value() / 10.0
        av_inf = self.doubleSpinBox_av_inf.value() / 10.0
        ah_sup = self.doubleSpinBox_ah_min_sup.value() / 10.0
        av_sup = self.doubleSpinBox_av_sup.value() / 10.0

        if self.fig_detalhamento:
            plt.close(self.fig_detalhamento)
            self.fig_detalhamento = None
        for i in reversed(range(self.layout_detalhamento.count())):
            w = self.layout_detalhamento.itemAt(i).widget()
            if w:
                w.setParent(None)

        try:
            (self.fig_detalhamento,
             self.d_prime_inf,
             self.d_prime_sup,
             setup_zoom_pan) = desenhar_detalhamento(
                dados=dados,
                as_inf=dict_inf, as_sup=dict_sup,
                c=c, phi_estribo=phi_estribo,
                ah_min_inf=ah_inf, ah_min_sup=ah_sup,
                av_inf=av_inf, av_sup=av_sup,
                folga_vibrador=folga_vib,
                h_laje=h_laje, largura_colaborante=b_laje,
                exibir_cotas=True, dpi=100, tamanho_fixo_qframe=True,
            )

            canvas_det = FigureCanvas(self.fig_detalhamento)
            setup_zoom_pan(canvas_det)
            self.layout_detalhamento.addWidget(canvas_det)
            self.exportar_deseneho_detalhamento.setEnabled(True)

        except Exception as e:
            self._exibir_texto_qframe(self.layout_detalhamento,
                                       f"Erro ao gerar detalhamento:\n{str(e)}")
            QMessageBox.critical(self, "Erro no Detalhamento", str(e))
            return

        h_total = self._get_h_total()

        if n_inf > 0:
            self.label_as_adotado_inf.setText(
                gerar_html_as_adotado(self.As_adotado_inferior, n_inf, phi_inf_mm))
            self.label_d_calculado_inf.setText(
                gerar_html_d_real(h_total - self.d_prime_inf))
        else:
            self.label_as_adotado_inf.setText(
                "Aₛ = 0 cm².<br>Não houve necessidade de armadura nas fibras inferiores.")
            self.label_d_calculado_inf.setText(
                "d_inf = 0 cm.<br>Não houve necessidade de armadura nas fibras inferiores.")

        if n_sup > 0:
            self.label_as_adotado_sup.setText(
                gerar_html_as_adotado(self.As_adotado_superior, n_sup, phi_sup_mm))
            self.label_d_calculado_sup.setText(
                gerar_html_d_real(h_total - self.d_prime_sup))
        else:
            self.label_as_adotado_sup.setText(
                "A'ₛ = 0 cm².<br>Não houve necessidade de armadura nas fibras superiores.")
            self.label_d_calculado_sup.setText(
                "d_sup = 0 cm.<br>Não houve necessidade de armadura nas fibras superiores.")

        self._toggle_d_real()

    def _toggle_d_real(self):
        """Atualiza os spinboxes de d real (automático ou manual)."""
        is_auto = self.d_automatico.isChecked()
        h_total = self._get_h_total()

        self.doubleSpinBox_d_real_inf.setRange(0.0, h_total)
        self.doubleSpinBox_d_real_sup.setRange(0.0, h_total)
        self.doubleSpinBox_d_real_inf.setReadOnly(is_auto)
        self.doubleSpinBox_d_real_sup.setReadOnly(is_auto)

        if is_auto:
            d_i = h_total - self.d_prime_inf if self.As_adotado_inferior > 0 else 0.0
            d_s = h_total - self.d_prime_sup if self.As_adotado_superior > 0 else 0.0
            self.doubleSpinBox_d_real_inf.setValue(d_i)
            self.doubleSpinBox_d_real_sup.setValue(d_s)
        self._update_readonly_style()

    # =========================================================================
    # GroupBox 5: Análise de Conformidade
    # =========================================================================

    def _analisar_conformidade(self):
        """Compara armaduras calculadas com as adotadas."""
        as_inf_calc = self.As_calc_inferior if self.As_calc_inferior is not None else 0.0
        as_sup_calc = self.As_calc_superior if self.As_calc_superior is not None else 0.0
        d_inf_dim, d_sup_dim = self._get_d_dimensionamento()

        html = gerar_html_comparacao(
            as_sup_calc=as_sup_calc,
            as_sup_adot=self.As_adotado_superior,
            as_inf_calc=as_inf_calc,
            as_inf_adot=self.As_adotado_inferior,
            d_sup_calc=self.doubleSpinBox_d_real_sup.value(),
            d_sup_adot=d_sup_dim,
            d_inf_calc=self.doubleSpinBox_d_real_inf.value(),
            d_inf_adot=d_inf_dim,
        )
        self.label_analise_conformidade.setText(html)

    # =========================================================================
    # GroupBox 6: Fadiga
    # =========================================================================

    def _toggle_n_fadiga(self):
        """Relação modular: automático (calculado) ou manual."""
        is_auto = self.n_automatico.isChecked()
        self.doubleSpinBox_n_eq.setReadOnly(is_auto)
        self.combo_tipo_agregado.setEnabled(is_auto)
        self.memorial_n_eq.setEnabled(is_auto)
        self._update_readonly_style()
        if is_auto:
            self._recalcular_n_fadiga()

    def _recalcular_n_fadiga(self):
        if not self.n_automatico.isChecked():
            return
        classe   = self.combo_classe_concreto.currentText()
        agregado = self.combo_tipo_agregado.currentText()
        eta, html = calcular_relacao_modular(classe, agregado)
        self.doubleSpinBox_n_eq.setValue(eta)
        self.n_eq_html_memorial = html

    def _toggle_delta_fadiga(self):
        """Amplitude de tensão: automático (calculado) ou manual."""
        is_auto = self.delta_fad_automatico.isChecked()
        self.doubleSpinBox_delta_sup.setReadOnly(is_auto)
        self.doubleSpinBox_delta_inf.setReadOnly(is_auto)
        self.memorial_delta.setEnabled(is_auto)
        self._update_readonly_style()

        if is_auto:
            phi_sup = (float(self.combo_diametro_as_sup.currentText()
                             .replace("ø ", "").replace(" mm", ""))
                       if self.As_adotado_superior > 0 else None)
            phi_inf = (float(self.combo_diametro_as_inf.currentText()
                             .replace("ø ", "").replace(" mm", ""))
                       if self.As_adotado_inferior > 0 else None)

            d_sup, d_inf, html = calcular_amplitude_tensao(phi_sup, phi_inf)
            if d_sup is not None:
                self.doubleSpinBox_delta_sup.setValue(d_sup)
            if d_inf is not None:
                self.doubleSpinBox_delta_inf.setValue(d_inf)
            self.delta_html_memorial = html

    def _verificar_fadiga(self):
        """Executa a verificação de fadiga."""
        m1 = self.m_max_els.value()
        m2 = self.m_min_els.value()

        n_eq     = self.doubleSpinBox_n_eq.value()
        df_inf   = self.doubleSpinBox_delta_inf.value()
        df_sup   = self.doubleSpinBox_delta_sup.value()

        bf     = self.doubleSpin_bf.value()
        h_laje = self.sec_super.h_laje if bf > 0 else 0.0
        b_laje = bf if bf > 0 else 0.0

        d_inf        = self.doubleSpinBox_d_real_inf.value()
        d_sup_fadiga = self.d_prime_sup if self.d_prime_sup > 0 else 0.0

        self.calc_fadiga = CalculadoraFlexaoFadiga(delta_f_fad_sd=175.0)

        if ((m1 == 0 and m2 == 0) or
                (self.As_adotado_inferior == 0 and self.As_adotado_superior == 0)):
            QMessageBox.warning(
                self, "Aviso",
                "Não há momentos ou armaduras suficientes para verificação de fadiga.")
            return

        try:
            self.calc_fadiga.verificar_fadiga(
                dados_secao=self.sec_super.dados,
                M_1=m1, M_2=m2,
                n_eq=n_eq,
                As_inf=self.As_adotado_inferior, d_inf=d_inf,
                As_sup=self.As_adotado_superior, d_sup=d_sup_fadiga,
                h_laje=h_laje, b_laje=b_laje,
                delta_f_fad_sd_inf=df_inf, delta_f_fad_sd_sup=df_sup,
            )
            html_resumo = obter_html_verificacao_fadiga(self.calc_fadiga)
            self.html_verificao_fadiga.setText(html_resumo)
            self.memorial_fadiga.setEnabled(True)
        except Exception as e:
            QMessageBox.critical(self, "Erro na Verificação", str(e))

    def _abrir_memorial_fadiga_completo(self):
        if not self.calc_fadiga:
            return
        _, html = self.calc_fadiga.obter_relatorio_resumido()
        self._abrir_memorial("Memorial Verificação Fadiga", html)

    # =========================================================================
    # Helpers: Memorial / Exportação
    # =========================================================================

    def _abrir_memorial(self, titulo: str, html_content: str):
        """Abre a janela genérica de memorial."""
        dlg = LogicaJanelaMemorial(titulo, html_content, parent=self)
        dlg.exec()

    def _exportar_grafico(self, figure):
        """Exporta figura para PNG ou DXF."""
        if not figure:
            return
        dlg = DialogoExportacao(self)
        if dlg.exec():
            formato = dlg.formato_escolhido
            caminho, _ = QFileDialog.getSaveFileName(
                self, "Salvar", "", f"{formato.upper()} (*.{formato})")
            if caminho:
                try:
                    if formato == "png":
                        figure.savefig(caminho, dpi=300)
                    else:
                        exportar_figura_para_dxf(figure, caminho)
                    QMessageBox.information(self, "Sucesso",
                                            "Gráfico exportado com sucesso!")
                except Exception as e:
                    QMessageBox.critical(self, "Erro",
                                         f"Ocorreu um erro ao exportar:\n{str(e)}")

    # =========================================================================
    # Manual do usuário
    # =========================================================================
    def abrir_manual(self):
        """
        Abre o manual do software no PDFViewer na seção de dimensionamento da
        armadura longitudinal.

        Navega diretamente para a página 71 do manual (índice 70 em base 0,
        pois o PyMuPDF (fitz) indexa páginas a partir de zero).
        """
        pdf_path = resource_path(os.path.join("assets", "Manual Girder25 Dark.pdf"))
        viewer = PDFViewer(pdf_path, "Manual: DIMENSIONAMENTO DA ARMADURA LONGITUDINAL")
        viewer.display_page(70)   # página 71 do manual → índice 70
        viewer.exec()