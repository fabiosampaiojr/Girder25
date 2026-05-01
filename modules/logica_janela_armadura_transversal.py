# ============================================================================
# Girder25 - logica_janela_armadura_transversal.py
# Autor: Fábio Henrique Sampaio Júnior
# Controlador do dimensionamento da armadura transversal (estribos).
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

from ui.janela_armadura_transversal import Ui_janela_armadura_transversal
from modules.logica_janela_memorial import LogicaJanelaMemorial
from modules.logica_janela_def_superestrutura import DialogoExportacao
from modules.exportar_dxf import exportar_figura_para_dxf
from modules.visualizador_pdf import PDFViewer
from modules.utils import resource_path

from modules.Calculadora_Cisalhamento import CalculadoraCisalhamento
from modules.Calculadora_Cisalhamento_Fadiga import CalculadoraCisalhamentoFadiga

from modules.funcoes_janela_armadura_transversal import (
    gerar_html_verificacao_biela,
    gerar_html_resumo_dimensionamento,
    gerar_html_espacamento_estribos,
    gerar_html_resumo_fadiga,
    calcular_delta_fad_estribo,
)
from modules.funcoes_sec_super import desenhar_secao
from modules.funcoes_janela_armadura_longitudinal import calcular_largura_colaborante
from modules.desenho_envelope import desenhar_envelope_calculo, ativar_interatividade_envelope


# Textos padrão exibidos antes da execução dos respectivos cálculos
_AGUARD_CALCULAR_ARMADURA = (
    "Cálculo ainda não realizado.<br>"
    "Informe os parâmetros e clique em <b>Calcular Armadura</b>."
)
_AGUARD_POSICIONAR = (
    "Detalhamento ainda não realizado.<br>"
    "Defina a armadura e clique em <b>Posicionar e Calcular</b>."
)
_AGUARD_FADIGA = (
    "Verificação à fadiga ainda não realizada.<br>"
    "Defina os parâmetros e clique em <b>Verificar Fadiga</b>."
)
_AGUARD_ENVELOPE = "Aguardando Cálculo dos Esforços"
_AGUARD_LAJE     = "Aguardando Geração do Desenho"


class LogicaJanelaArmaduraTransversal(QDialog, Ui_janela_armadura_transversal):
    """
    Controlador do dimensionamento da armadura transversal (Modelo I, NBR 6118:2023).

    Fluxo de uso
    ------------
    1. Selecionar seção crítica e conferir esforços cortantes (ELU/ELS).
    2. Definir parâmetros (fck, α, d) e clicar em **Calcular Armadura**.
    3. Detalhar o espaçamento (diâmetro, ramos, Asw) e clicar em **Posicionar e Calcular**.
    4. Opcionalmente, executar a verificação à fadiga.
    """

    def __init__(self, gerenciador, parent=None):
        super().__init__(parent)
        self.setupUi(self)
        self.setWindowTitle("Dimensionamento da Armadura Transversal")
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
        self.fig_dcl  = None    # Figura do envelope de cortante
        self.fig_laje = None    # Figura da seção com laje colaborante

        self._delta_fad_html_memorial: str = ""

        self.calc_cisalhamento: CalculadoraCisalhamento | None = None
        self.calc_fadiga:       CalculadoraCisalhamentoFadiga | None = None

        self._d_critico: float = 0.0
        self._bf_html_memorial: str = ""

        # ── Inicialização da interface ────────────────────────────────────────
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
        for fig in (self.fig_dcl, self.fig_laje):
            if fig:
                plt.close(fig)
        self.fig_dcl = None
        self.fig_laje = None
        super().closeEvent(event)

    # =========================================================================
    # INICIALIZAÇÃO
    # =========================================================================

    def _criar_grupos_botoes(self):
        """Cria QButtonGroup para cada par de radiobuttons exclusivos."""
        self.grupo_estado_envelope = QButtonGroup(self)
        self.grupo_estado_envelope.addButton(self.radioELU)
        self.grupo_estado_envelope.addButton(self.radioELS)

        self.grupo_vsd = QButtonGroup(self)
        self.grupo_vsd.addButton(self.vsd_automatico)
        self.grupo_vsd.addButton(self.vsd_manual)

        self.grupo_laje = QButtonGroup(self)
        self.grupo_laje.addButton(self.laje_automatico)
        self.grupo_laje.addButton(self.laje_manual)
        self.grupo_laje.addButton(self.laje_n_considerar)

        self.grupo_asw = QButtonGroup(self)
        self.grupo_asw.addButton(self.asw_automatico)
        self.grupo_asw.addButton(self.asw_manual)

        self.grupo_delta_fad = QButtonGroup(self)
        self.grupo_delta_fad.addButton(self.delta_fad_automatico)
        self.grupo_delta_fad.addButton(self.delta_fad_manual)

    def _aplicar_estados_padrao(self):
        """Marca os radiobuttons padrão sem disparar sinais de lógica."""
        self.radioELU.setChecked(True)
        self.vsd_automatico.setChecked(True)
        self.laje_automatico.setChecked(True)
        self.asw_automatico.setChecked(True)
        self.delta_fad_automatico.setChecked(True)

    def _configurar_ui_inicial(self):
        """Configura layouts, sufixos, ranges e textos de estado inicial."""

        self.layout_dcl = QVBoxLayout(self.desenho_dlc_secao)
        self.layout_dcl.setContentsMargins(0, 0, 0, 0)
        self._exibir_texto_qframe(self.layout_dcl, _AGUARD_ENVELOPE)

        self.layout_laje = QVBoxLayout(self.frame_desenho_laje)
        self.layout_laje.setContentsMargins(0, 0, 0, 0)
        self._exibir_texto_qframe(self.layout_laje, _AGUARD_LAJE)

        for spin in [self.v_max_elu, self.v_min_elu,
                     self.v_max_els, self.v_min_els]:
            spin.setSuffix(" kN")

        self.doubleSpin_bf.setSuffix(" cm")
        self.doubleSpinBox_d_inf.setSuffix(" cm")
        self.doubleSpinBox_d_sup.setSuffix(" cm")
        self.doubleSpinBox_asw.setSuffix(" cm²/m")
        self.doubleSpinBox_delta.setSuffix(" MPa")

        h_total = self._get_h_total()
        self._configurar_ranges_d(h_total)

        self.spinBox_alpha.setRange(45, 90)
        self.spinBox_alpha.setValue(90)
        self.spinBox_alpha.setSuffix("°")

        self.spinBox_ramos.setRange(1, 10)
        self.spinBox_ramos.setValue(2)

        self.doubleSpinBox_delta.setRange(0.01, 9999.0)
        self.doubleSpinBox_asw.setRange(0.01, 9999.0)

        self.combo_estribo.setCurrentText("ø 12.5 mm")

        self.html_verificacao_biela.setText(_AGUARD_CALCULAR_ARMADURA)
        self.html_resumo_dimensionamento.setText(_AGUARD_CALCULAR_ARMADURA)
        self.html_espacamento_estribos.setText(_AGUARD_POSICIONAR)
        self.html_resumo_fadiga.setText(_AGUARD_FADIGA)

        self.memorial_asw.setEnabled(False)
        self.memorial_fadiga.setEnabled(False)
        self.exportar_frame_desenho_laje.setEnabled(False)
        self.memorial_delta.setEnabled(False)

        self._aplicar_estilo_readonly()

    def _configurar_ranges_d(self, h_total: float):
        if h_total <= 0:
            return
        self.doubleSpinBox_d_inf.setRange(0.0, h_total)
        self.doubleSpinBox_d_sup.setRange(0.0, h_total)
        self.doubleSpinBox_d_inf.setValue(round(0.85 * h_total, 2))
        self.doubleSpinBox_d_sup.setValue(round(0.90 * h_total, 2))

    def _conectar_sinais(self):
        """Conecta todos os sinais de widgets aos seus slots."""
        self.radioELU.clicked.connect(self._atualizar_envelope)
        self.radioELS.clicked.connect(self._atualizar_envelope)

        self.combo_secao.currentIndexChanged.connect(self._atualizar_secao_selecionada)

        self.vsd_automatico.toggled.connect(self._toggle_vsd)
        self.vsd_manual.toggled.connect(self._toggle_vsd)

        self.laje_automatico.toggled.connect(self._toggle_laje)
        self.laje_manual.toggled.connect(self._toggle_laje)
        self.laje_n_considerar.toggled.connect(self._toggle_laje)
        self.combo_posicao_longarina.currentIndexChanged.connect(
            self._recalcular_laje_colaborante)

        self.memorial_bf.clicked.connect(
            lambda: self._abrir_memorial(
                "Memorial de Cálculo Laje: Largura Colaborante (bf)",
                self._bf_html_memorial))
        self.atualizar_desenho_laje.clicked.connect(self._atualizar_desenho_laje)
        self.exportar_frame_desenho_laje.clicked.connect(
            lambda: self._exportar_grafico(self.fig_laje))
        self.exportar_desenho_dlc_secao.clicked.connect(
            lambda: self._exportar_grafico(self.fig_dcl))

        self.calcular_armadura.clicked.connect(self._calcular_armadura_transversal)
        self.memorial_asw.clicked.connect(self._abrir_memorial_cisalhamento)

        self.combo_estribo.currentIndexChanged.connect(self._recalcular_delta_automatico)

        self.asw_automatico.toggled.connect(self._toggle_asw)
        self.asw_manual.toggled.connect(self._toggle_asw)
        self.posicionar_e_calcular.clicked.connect(self._posicionar_e_calcular)

        self.delta_fad_automatico.toggled.connect(self._toggle_delta_fadiga)
        self.delta_fad_manual.toggled.connect(self._toggle_delta_fadiga)
        self.memorial_delta.clicked.connect(
            lambda: self._abrir_memorial(
                "Memorial Amplitude de Tensão Admissível (Δfsd,fad)",
                self._delta_fad_html_memorial))
        self.vereficiar_fadiga.clicked.connect(self._verificar_fadiga)
        self.memorial_fadiga.clicked.connect(self._abrir_memorial_fadiga)

        # Manual do usuário
        self.manual.clicked.connect(self.abrir_manual)

        self.cancelar.clicked.connect(self.reject)
        self.confirmar.clicked.connect(self.accept)

    def _ajustar_scroll_area(self):
        """Expande a área de rolagem se o conteúdo ultrapassar a altura visível."""
        last_widget = getattr(self, 'groupBox_verificacao_fadiga', None)
        if last_widget is None:
            return
        total_height = last_widget.geometry().bottom() + 30
        current_geo  = self.scrollAreaWidgetContents.geometry()
        if total_height > current_geo.height():
            self.scrollAreaWidgetContents.setGeometry(
                current_geo.x(), current_geo.y(),
                current_geo.width(), total_height,
            )

    def _carregar_dados(self):
        """
        Popula o combo de seções, configura os ranges de d com a altura real
        e plota o envelope de cortante inicial (ELU).
        """
        if not self.esforcos_obj or not getattr(self.esforcos_obj, 'resultados', None):
            return

        tabela_cortante_elu = self.esforcos_obj.resultados["ELU"]["Cortante"]
        self.combo_secao.clear()
        for row in tabela_cortante_elu[1:]:
            pos  = row[0]
            nome = row[1]
            self.combo_secao.addItem(str(nome), userData={"nome": nome, "pos": pos})

        h_total = self._get_h_total()
        self._configurar_ranges_d(h_total)
        self._recalcular_delta_automatico()
        self._atualizar_envelope()

    # =========================================================================
    # HELPERS GERAIS
    # =========================================================================

    def _get_h_total(self) -> float:
        h_long = self.sec_super.dados.get("h", 0)
        h_laje = (self.sec_super.h_laje
                  if getattr(self, 'doubleSpin_bf', None) is not None
                     and self.doubleSpin_bf.value() > 0
                  else 0)
        return h_long + h_laje

    def _get_bw(self) -> float:
        dados = self.sec_super.dados
        for chave in ("bw", "b_alma", "b_w", "bw_cm"):
            if chave in dados and dados[chave] > 0:
                return float(dados[chave])
        for chave in ("b", "largura", "b_total"):
            if chave in dados and dados[chave] > 0:
                return float(dados[chave])
        return 0.0

    def _get_d_critico(self) -> float | None:
        d_inf = self.doubleSpinBox_d_inf.value()
        d_sup = self.doubleSpinBox_d_sup.value()
        if d_inf == 0.0 and d_sup == 0.0:
            return None
        if d_inf == 0.0:
            return d_sup
        if d_sup == 0.0:
            return d_inf
        return min(d_inf, d_sup)

    def _get_diametro_estribo_mm(self) -> float:
        texto = self.combo_estribo.currentText()
        return float(texto.replace("ø ", "").replace(" mm", ""))

    def _exibir_texto_qframe(self, layout, texto):
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
        ro_style = """
            QDoubleSpinBox[readOnly="true"] {
                background-color: #2d2d2d;
                color: #ffffff;
                border: 1px solid #555;
            }
        """
        for spin in self.findChildren(QDoubleSpinBox):
            spin.setStyleSheet(ro_style if spin.isReadOnly() else "")

    # =========================================================================
    # GroupBox 1 — Envelope de Cortante e Seção Selecionada
    # =========================================================================

    def _atualizar_envelope(self):
        if not self.esforcos_obj or not getattr(self.esforcos_obj, 'resultados', None):
            self._exibir_texto_qframe(self.layout_dcl, _AGUARD_ENVELOPE)
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
                esforco="cortante",
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
        idx = self.combo_secao.currentIndex()
        if idx < 0:
            return
        dados_sec = self.combo_secao.itemData(idx)
        if not dados_sec:
            return

        nome = dados_sec["nome"]

        if self.vsd_automatico.isChecked():
            for row in self.esforcos_obj.resultados["ELU"]["Cortante"][1:]:
                if row[1] == nome:
                    self.v_max_elu.setValue(float(row[2]))
                    self.v_min_elu.setValue(float(row[3]))
                    break
            for row in self.esforcos_obj.resultados["ELS"]["Cortante"][1:]:
                if row[1] == nome:
                    self.v_max_els.setValue(float(row[2]))
                    self.v_min_els.setValue(float(row[3]))
                    break

        self._recalcular_laje_colaborante()

    def _toggle_vsd(self):
        is_auto = self.vsd_automatico.isChecked()
        for spin in [self.v_max_elu, self.v_min_elu,
                     self.v_max_els, self.v_min_els]:
            spin.setReadOnly(is_auto)
            spin.setMinimum(-999999.0)
            spin.setMaximum(+999999.0)

        self._update_readonly_style()
        if is_auto:
            self._atualizar_secao_selecionada()

    def _toggle_laje(self):
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

    def _recalcular_laje_colaborante(self):
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
            _, mem_html, bf_val = calcular_largura_colaborante(
                self.sup, self.sec_super, x_val, tipo_viga)
            self.doubleSpin_bf.setRange(0, 99999.0)
            self.doubleSpin_bf.setValue(bf_val * 100.0)
            self._bf_html_memorial = mem_html
        except Exception as e:
            self.doubleSpin_bf.setValue(0.0)
            self._bf_html_memorial = f"Erro no cálculo: {str(e)}"
            QMessageBox.warning(self, "Erro",
                                f"Não foi possível calcular a largura colaborante:\n{e}")

    def _atualizar_desenho_laje(self):
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
    # GroupBox 2 — Parâmetros de Cálculo e Dimensionamento ao Cisalhamento
    # =========================================================================

    def _calcular_armadura_transversal(self):
        d_critico = self._get_d_critico()
        if d_critico is None:
            QMessageBox.critical(
                self, "Parâmetro Inválido",
                "<b>Não é possível dimensionar a armadura de cisalhamento sem "
                "definir ao menos um valor de d efetivo.</b><br><br>"
                "Os parâmetros d<sub>inf</sub> e d<sub>sup</sub> determinam a "
                "distância da fibra mais tracionada ao centroide da armadura. "
                "Ao menos um deles deve ser maior que zero para que o Modelo I "
                "(NBR 6118:2023) possa ser aplicado.<br><br>"
                "• Se houver apenas armadura inferior: informe d<sub>inf</sub> "
                "e deixe d<sub>sup</sub> = 0.<br>"
                "• Se houver apenas armadura superior: informe d<sub>sup</sub> "
                "e deixe d<sub>inf</sub> = 0.<br>"
                "• Se houver ambas: o menor valor (d crítico) será adotado, "
                "garantindo um dimensionamento a favor da segurança."
            )
            return

        self._d_critico = d_critico

        v_max = self.v_max_elu.value()
        v_min = self.v_min_elu.value()
        Vsd   = max(abs(v_max), abs(v_min))

        bw = self._get_bw()
        if bw <= 0:
            QMessageBox.critical(
                self, "Erro de Dados",
                "Não foi possível obter a largura da alma (bw) da seção.\n"
                "Verifique a definição da geometria da superestrutura."
            )
            return

        fck   = float(self.combo_classe_concreto.currentText().replace("C", ""))
        alpha = float(self.spinBox_alpha.value())
        fyk   = 500.0

        try:
            self.calc_cisalhamento = CalculadoraCisalhamento()
            resultado = self.calc_cisalhamento.dimensionar_modelo_I(
                Vsd                 = Vsd,
                bw                  = bw,
                d                   = self._d_critico,
                fck                 = fck,
                fyk                 = fyk,
                alpha_estribo_graus = alpha,
            )
        except Exception as e:
            QMessageBox.critical(self, "Erro no Dimensionamento",
                                 f"Ocorreu um erro ao executar a calculadora:\n{str(e)}")
            return

        self.html_verificacao_biela.setText(gerar_html_verificacao_biela(resultado))
        self.html_resumo_dimensionamento.setText(
            gerar_html_resumo_dimensionamento(resultado))

        self.memorial_asw.setEnabled(True)
        self._toggle_asw()
        self._recalcular_delta_automatico()

    def _abrir_memorial_cisalhamento(self):
        if not self.calc_cisalhamento:
            return
        _, html = self.calc_cisalhamento.obter_relatorio_resumido()
        self._abrir_memorial("Memorial de Cálculo — Cisalhamento (Modelo I)", html)

    # =========================================================================
    # GroupBox 3 — Detalhamento (Espaçamento dos Estribos)
    # =========================================================================

    def _toggle_asw(self):
        is_auto = self.asw_automatico.isChecked()
        self.doubleSpinBox_asw.setReadOnly(is_auto)

        if is_auto and self.calc_cisalhamento and self.calc_cisalhamento.ultimo_resultado:
            asw_adotar = self.calc_cisalhamento.ultimo_resultado.asw_adotar_cm2_m
            self.doubleSpinBox_asw.setValue(asw_adotar)

        self._update_readonly_style()

    def _posicionar_e_calcular(self):
        if self._d_critico <= 0:
            QMessageBox.warning(
                self, "Aviso",
                "Calcule a armadura de cisalhamento antes de detalhar o espaçamento."
            )
            return

        asw_nec    = self.doubleSpinBox_asw.value()
        diametro   = self._get_diametro_estribo_mm()
        n_ramos    = self.spinBox_ramos.value()
        d_cm       = self._d_critico

        try:
            _, html = gerar_html_espacamento_estribos(
                asw_necessario = asw_nec,
                d_cm           = d_cm,
                diametro_mm    = diametro,
                n_ramos        = n_ramos,
                fyk            = 500.0,
            )
            self.html_espacamento_estribos.setText(html)
        except Exception as e:
            QMessageBox.critical(self, "Erro no Detalhamento",
                                 f"Erro ao calcular espaçamento:\n{str(e)}")

    # =========================================================================
    # GroupBox 4 — Verificação à Fadiga
    # =========================================================================

    def _recalcular_delta_automatico(self):
        if not self.delta_fad_automatico.isChecked():
            return

        diametro_mm = self._get_diametro_estribo_mm()

        try:
            delta, html = calcular_delta_fad_estribo(
                diametro_mm      = diametro_mm,
                diametro_pino_mm = None,
                condicao         = 'padrao',
                ativo            = True,
            )
            self.doubleSpinBox_delta.setValue(delta)
            self._delta_fad_html_memorial = html
            self.memorial_delta.setEnabled(True)
        except Exception as e:
            self.memorial_delta.setEnabled(False)
            QMessageBox.warning(
                self, "Aviso — Amplitude de Fadiga",
                f"Não foi possível calcular Δfsd,fad automaticamente:\n{str(e)}\n\n"
                "Utilize o modo manual para inserir o valor."
            )

    def _toggle_delta_fadiga(self):
        is_auto = self.delta_fad_automatico.isChecked()
        self.doubleSpinBox_delta.setReadOnly(is_auto)
        self.memorial_delta.setEnabled(is_auto and bool(self._delta_fad_html_memorial))
        self._update_readonly_style()

        if is_auto:
            self._recalcular_delta_automatico()

    def _verificar_fadiga(self):
        if self._d_critico <= 0:
            QMessageBox.warning(
                self, "Aviso",
                "Execute o dimensionamento ao cisalhamento antes de verificar a fadiga."
            )
            return

        bw = self._get_bw()
        if bw <= 0:
            QMessageBox.critical(self, "Erro de Dados",
                                 "Largura da alma (bw) inválida. Verifique a geometria.")
            return

        fck           = float(self.combo_classe_concreto.currentText().replace("C", ""))
        Vd1_serv      = self.v_max_els.value()
        Vd2_serv      = self.v_min_els.value()
        asw_adotado   = self.doubleSpinBox_asw.value()
        delta_fsd_fad = self.doubleSpinBox_delta.value()
        alpha         = float(self.spinBox_alpha.value())

        if asw_adotado <= 0:
            QMessageBox.warning(
                self, "Aviso",
                "A área de armadura transversal (Asw/s) deve ser maior que zero."
            )
            return

        try:
            self.calc_fadiga = CalculadoraCisalhamentoFadiga(
                gamma_c       = 1.4,
                delta_fsd_fad = delta_fsd_fad,
            )
            resultado_fadiga = self.calc_fadiga.verificar_fadiga(
                bw                  = bw,
                d                   = self._d_critico,
                asw_s_adotado       = asw_adotado,
                fck                 = fck,
                alpha_estribo_graus = alpha,
                Vd1_serv            = Vd1_serv,
                Vd2_serv            = Vd2_serv,
            )
        except Exception as e:
            QMessageBox.critical(self, "Erro na Verificação à Fadiga",
                                 f"Erro ao executar a calculadora:\n{str(e)}")
            return

        self.html_resumo_fadiga.setText(gerar_html_resumo_fadiga(resultado_fadiga))
        self.memorial_fadiga.setEnabled(True)

    def _abrir_memorial_fadiga(self):
        if not self.calc_fadiga:
            return
        _, html = self.calc_fadiga.obter_relatorio_resumido()
        self._abrir_memorial("Memorial de Cálculo — Fadiga da Armadura Transversal",
                              html)

    # =========================================================================
    # Helpers: Memorial e Exportação de Gráficos
    # =========================================================================

    def _abrir_memorial(self, titulo: str, html_content: str):
        dlg = LogicaJanelaMemorial(titulo, html_content, parent=self)
        dlg.exec()

    def _exportar_grafico(self, figure):
        if not figure:
            return
        dlg = DialogoExportacao(self)
        if dlg.exec():
            formato = dlg.formato_escolhido
            caminho, _ = QFileDialog.getSaveFileName(
                self, "Salvar Gráfico", "",
                f"{formato.upper()} (*.{formato})"
            )
            if caminho:
                try:
                    if formato == "png":
                        figure.savefig(caminho, dpi=300)
                    else:
                        exportar_figura_para_dxf(figure, caminho)
                    QMessageBox.information(self, "Sucesso",
                                            "Gráfico exportado com sucesso!")
                except Exception as e:
                    QMessageBox.critical(self, "Erro na Exportação",
                                         f"Ocorreu um erro ao exportar:\n{str(e)}")

    # =========================================================================
    # Manual do usuário
    # =========================================================================
    def abrir_manual(self):
        """
        Abre o manual do software no PDFViewer na seção de dimensionamento da
        armadura transversal.

        Navega diretamente para a página 78 do manual (índice 77 em base 0,
        pois o PyMuPDF (fitz) indexa páginas a partir de zero).
        """
        pdf_path = resource_path(os.path.join("assets", "Manual Girder25 Dark.pdf"))
        viewer = PDFViewer(pdf_path, "Manual: DIMENSIONAMENTO DA ARMADURA TRANSVERSAL")
        viewer.display_page(77)   # página 78 do manual → índice 77
        viewer.exec()