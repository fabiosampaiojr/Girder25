# ============================================================================
# Girder25 - logica_janela_sobrecarga.py
# Autor: Fábio Henrique Sampaio Júnior
# Controlador da análise da sobrecarga permanente (g2).
# ============================================================================

import os
from PyQt6.QtWidgets import (
    QDialog, QMessageBox, QVBoxLayout, QLabel, QButtonGroup
)
from PyQt6.QtCore import Qt
import matplotlib.pyplot as plt
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas

from ui.janela_sobrecarga import Ui_janela_sobrecarga
from modules.desenho_sec_transversal import desenhar_sec_transversal
from modules.gerar_html import (
    gerar_html_pavimento,
    gerar_html_repavimentacao,
    gerar_html_guarda_rodas,
    gerar_html_sobrecarga_passeio,
    gerar_html_g2_total,
    gerar_html_resultados_esforcos_calculos,
)
from modules.desenho_ponte_carregada import desenhar_ponte_carregada
from modules.Calculadora_Elementos_Finitos import CalculadoraElementosFinitos
from modules.logica_resultados_sobrecarga import (
    LogicaJanelaResultadosEsforcos,
    LogicaJanelaResultadosReacoes,
)
from modules.visualizador_pdf import PDFViewer
from modules.utils import resource_path

# Mapeamento de classes normativas para dimensões da via
MAPA_CLASSES: dict[str, dict] = {
    "0":     {"faixa": 375, "acostamento_ext": 300, "acostamento_int": 60, "total": 1190},
    "I - A": {"faixa": 360, "acostamento_ext": 300, "acostamento_int": 60, "total": 1160},
    "I - B": {"faixa": 350, "acostamento": 250,  "total": 1280},
    "II":    {"faixa": 350, "acostamento": 250,  "total": 1280},
    "III":   {"faixa": 350, "acostamento": 150,  "total": 1080},
    "IV":    {"faixa": 300, "acostamento": 150,  "total": 980},
}

CLASSES_PISTA_DUPLA: set[str] = {"0", "I - A"}

MAPA_TIPOS: dict[str, str] = {
    "Isostática: Múltiplos Vãos Biapoioados":     "biapoiada",
    "Isostática: Biapoiada com Balanço":           "isostatica_em_balanco",
    "Hiperestática: Vão Contínuo sem Balanço":     "hiperestatica_sem_balanco",
    "Hiperestática: Vão Contínuo com Balanço":     "hiperestatica_com_balanco",
}

_HTML_SEM_PASSEIO = (
    "<html><body style='font-family: \"Times New Roman\", serif; font-size: 13pt; "
    "color: white; font-style: italic;'>"
    "Seção Transversal não possui passeio."
    "</body></html>"
)


class LogicaJanelaSobrecarga(QDialog, Ui_janela_sobrecarga):
    """
    Diálogo para definição e análise das cargas de sobrecarga permanente (g2).
    Permite cálculo automático das parcelas de pavimento, repavimentação,
    guarda-rodas, passeio e guarda-corpo, com opção de entrada manual.
    Realiza análise MEF para obtenção de esforços e reações.
    """

    def __init__(self, gerenciador):
        super().__init__()
        self.setupUi(self)
        self.gerenciador = gerenciador

        # Figuras do Matplotlib
        self.fig_secao: plt.Figure | None = None
        self.fig_ponte: plt.Figure | None = None
        self.fig_cortante: plt.Figure | None = None
        self.fig_momento:  plt.Figure | None = None

        # Calculadora MEF
        self.calculadora = None

        # Valor efetivo de g2 (kN/m por longarina)
        self.g2_valor_calculado: float = 0.0

        # Tabelas de resultados
        self.tabela_reacoes:  list = []
        self.tabela_cortante: list = []
        self.tabela_momento:  list = []

        # Valores extremos
        self.valores_limites = {}

        # Layouts das áreas de desenho
        self.layout_desenho   = QVBoxLayout(self.desenho)
        self.layout_desenho_2 = QVBoxLayout(self.desenho_2)

        # Grupo de exclusividade entre rádios automático/manual
        self.grupo_modo_g2 = QButtonGroup(self)
        self.grupo_modo_g2.addButton(self.radio_automatico)
        self.grupo_modo_g2.addButton(self.radio_manual)

        self._configurar_interface()
        self._configurar_sinais()
        self._verificar_estados_iniciais()

        self._renderizar_desenho_secao()
        self._atualizar_todos_htmls()

        # Inicia no modo automático
        self.alternar_modo_g2(True)

    # -------------------------------------------------------------------------
    # Gerenciamento da janela
    # -------------------------------------------------------------------------
    def closeEvent(self, event):
        """Libera todas as figuras do Matplotlib ao fechar o diálogo."""
        for fig in (self.fig_secao, self.fig_ponte, self.fig_cortante, self.fig_momento):
            if fig:
                plt.close(fig)
        self.fig_secao = None
        self.fig_ponte = None
        self.fig_cortante = None
        self.fig_momento = None
        super().closeEvent(event)

    # -------------------------------------------------------------------------
    # Configuração inicial da interface
    # -------------------------------------------------------------------------
    def _configurar_interface(self):
        """Aplica limites, passos e valores padrão aos spinboxes."""
        self.spin_gama_pavimento.setRange(15.0, 30.0)
        self.spin_gama_pavimento.setSingleStep(0.5)
        self.spin_gama_pavimento.setDecimals(1)
        self.spin_gama_pavimento.setValue(24.0)
        self.spin_gama_pavimento.setSuffix(" kN/m³")

        self.spin_q_repavimentacao.setRange(1.0, 10.0)
        self.spin_q_repavimentacao.setSingleStep(0.5)
        self.spin_q_repavimentacao.setDecimals(1)
        self.spin_q_repavimentacao.setValue(2.0)
        self.spin_q_repavimentacao.setSuffix(" kN/m²")

        self.spin_gama_c.setRange(18.0, 25.0)
        self.spin_gama_c.setSingleStep(0.5)
        self.spin_gama_c.setDecimals(1)
        self.spin_gama_c.setValue(25.0)
        self.spin_gama_c.setSuffix(" kN/m³")

        self.spin_area_guarda_rodas.setRange(0.20, 0.50)
        self.spin_area_guarda_rodas.setSingleStep(0.01)
        self.spin_area_guarda_rodas.setDecimals(4)
        self.spin_area_guarda_rodas.setValue(0.25)
        self.spin_area_guarda_rodas.setSuffix(" m²")

        self.spin_gama_h_passeio.setRange(0.05, 0.20)
        self.spin_gama_h_passeio.setSingleStep(0.01)
        self.spin_gama_h_passeio.setDecimals(2)
        self.spin_gama_h_passeio.setValue(0.08)
        self.spin_gama_h_passeio.setSuffix(" m")

        self.spin_q_guarda_corpo.setRange(0.5, 3.0)
        self.spin_q_guarda_corpo.setSingleStep(0.1)
        self.spin_q_guarda_corpo.setDecimals(1)
        self.spin_q_guarda_corpo.setValue(1.0)
        self.spin_q_guarda_corpo.setSuffix(" kN/m")

        self.spin_q_aterro.setRange(10.0, 100.0)
        self.spin_q_aterro.setSingleStep(1.0)
        self.spin_q_aterro.setDecimals(1)
        self.spin_q_aterro.setValue(30.0)
        self.spin_q_aterro.setSuffix(" kN/m")

        lbl = QLabel("Aguardando Geração do Desenho")
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.layout_desenho_2.addWidget(lbl)

        self.html_resultados_esforcos.setPlainText("Aguardando Cálculos")
        self.botao_cortante.setEnabled(False)
        self.botao_momento.setEnabled(False)
        self.botao_reacoes.setEnabled(False)

        # Spinbox manual de g2
        self.doubleSpinBox_g2.setRange(0.01, 1000.0)
        self.doubleSpinBox_g2.setSingleStep(0.5)
        self.doubleSpinBox_g2.setDecimals(2)
        self.doubleSpinBox_g2.setSuffix(" kN/m")
        self.doubleSpinBox_g2.setEnabled(False)
        self.doubleSpinBox_g2.clear()
        self.doubleSpinBox_g2.lineEdit().setPlaceholderText("")

        self.radio_automatico.setChecked(True)

    def _configurar_sinais(self):
        """Conecta os sinais dos widgets às funções de tratamento."""
        self.spin_gama_pavimento.valueChanged.connect(self._ao_alterar_pavimento)
        self.spin_q_repavimentacao.valueChanged.connect(self._ao_alterar_repavimentacao)
        self.spin_gama_c.valueChanged.connect(self._ao_alterar_guarda_rodas)
        self.spin_area_guarda_rodas.valueChanged.connect(self._ao_alterar_guarda_rodas)
        self.spin_gama_h_passeio.valueChanged.connect(self._ao_alterar_passeio)
        self.spin_q_guarda_corpo.valueChanged.connect(self._ao_alterar_passeio)
        self.check_transversina.toggled.connect(self._toggle_aterro)
        self.atualizar.clicked.connect(self._processar_desenho_ponte)
        self.calcular.clicked.connect(self._processar_calculos)
        self.botao_cortante.clicked.connect(self._abrir_janela_cortante)
        self.botao_momento.clicked.connect(self._abrir_janela_momento)
        self.botao_reacoes.clicked.connect(self._abrir_janela_reacoes)
        self.cancelar.clicked.connect(self.reject)
        self.confirmar.clicked.connect(self._acao_confirmar)
        self.manual.clicked.connect(self.abrir_manual)

        # Rádios automático / manual
        self.radio_automatico.toggled.connect(self.alternar_modo_g2)
        self.radio_manual.toggled.connect(self.alternar_modo_g2)
        self.doubleSpinBox_g2.valueChanged.connect(self._atualizar_todos_htmls)

    def _verificar_estados_iniciais(self):
        """Desabilita controles dependentes da presença de laje e passeio."""
        sup = self.gerenciador.get_superestrutura()
        sec = self.gerenciador.get_secao_transversal()

        tem_laje = bool(sup and sup.laje_transicao)
        self.check_transversina.setEnabled(tem_laje)
        self.check_transversina.setChecked(False)
        self._toggle_aterro(False)

        tem_passeio = bool(sec and sec.passeio)
        self._toggle_controles_passeio(tem_passeio)

    # =========================================================================
    # Alternância entre modo automático e manual
    # =========================================================================
    def alternar_modo_g2(self, checked):
        """
        Gerencia a interface conforme o modo selecionado.
        O valor efetivo de g2 é calculado em _atualizar_html_g2_total.
        """
        if self.radio_automatico.isChecked():
            self._set_spins_enabled(True)
            self.doubleSpinBox_g2.setEnabled(False)
            self.doubleSpinBox_g2.setSuffix("")
            self.doubleSpinBox_g2.clear()
            self.doubleSpinBox_g2.lineEdit().setPlaceholderText("")
            self._atualizar_todos_htmls(ativo=True)
        else:
            self._set_spins_enabled(False)
            self.doubleSpinBox_g2.setEnabled(True)
            self.doubleSpinBox_g2.setSuffix(" kN/m")

            if self.g2_valor_calculado > 0:
                self.doubleSpinBox_g2.setValue(self.g2_valor_calculado)
            else:
                self._atualizar_todos_htmls(ativo=True)
                self.doubleSpinBox_g2.setValue(self.g2_valor_calculado)

            self._atualizar_todos_htmls(ativo=False)

    def _set_spins_enabled(self, enabled: bool):
        """Habilita/desabilita todos os spinboxes de entrada de dados."""
        self.spin_gama_pavimento.setEnabled(enabled)
        self.spin_q_repavimentacao.setEnabled(enabled)
        self.spin_gama_c.setEnabled(enabled)
        self.spin_area_guarda_rodas.setEnabled(enabled)
        self.spin_gama_h_passeio.setEnabled(enabled)
        self.spin_q_guarda_corpo.setEnabled(enabled)

    # -------------------------------------------------------------------------
    # Controles de habilitação específicos
    # -------------------------------------------------------------------------
    def _toggle_aterro(self, estado: bool):
        """Habilita/desabilita o campo de carga de aterro sobre a laje."""
        self.label_aterro.setEnabled(estado)
        self.spin_q_aterro.setEnabled(estado)
        self._atualizar_html_g2_total()

    def _toggle_controles_passeio(self, tem_passeio: bool):
        """Habilita/desabilita os campos relacionados ao passeio."""
        self.label_6.setEnabled(tem_passeio)
        self.label_7.setEnabled(tem_passeio)
        self.spin_gama_h_passeio.setEnabled(tem_passeio)
        self.spin_q_guarda_corpo.setEnabled(tem_passeio)

        if not tem_passeio:
            self.html_sobrecarga_passeio.setText(_HTML_SEM_PASSEIO)

    # -------------------------------------------------------------------------
    # Handlers de alteração de valores (disparam atualização dos HTMLs)
    # -------------------------------------------------------------------------
    def _ao_alterar_pavimento(self):
        self._atualizar_html_pavimento()
        self._atualizar_html_passeio()
        self._atualizar_html_g2_total()

    def _ao_alterar_repavimentacao(self):
        self._atualizar_html_repavimentacao()
        self._atualizar_html_g2_total()

    def _ao_alterar_guarda_rodas(self):
        self._atualizar_html_guarda_rodas()
        self._atualizar_html_g2_total()

    def _ao_alterar_passeio(self):
        self._atualizar_html_passeio()
        self._atualizar_html_g2_total()

    # =========================================================================
    # Obtenção de parâmetros base da seção transversal
    # =========================================================================
    def _obter_parametros_base(self) -> dict | None:
        """Retorna um dicionário com dados geométricos essenciais ou None."""
        sec       = self.gerenciador.get_secao_transversal()
        sec_super = self.gerenciador.get_secao_superestrutura()

        if not sec or not sec_super:
            return None

        config = sec.obter_config_via()
        if not config:
            return None

        l_pavimento = (config["total"] - 80) / 100.0  # desconta as 2 NJ de 40 cm
        h_borda  = sec.h_borda  / 100.0
        h_centro = sec.h_centro / 100.0
        l_passeio = (sec.passeio / 100.0) if sec.passeio else None

        return {
            "sec":          sec,
            "sec_super":    sec_super,
            "classe":       sec.classe,
            "l_pavimento":  l_pavimento,
            "h_borda":      h_borda,
            "h_centro":     h_centro,
            "l_passeio":    l_passeio,
            "n_longarinas": sec_super.n_longarinas,
        }

    # =========================================================================
    # Cálculo das componentes de g2 (kN/m total na ponte)
    # =========================================================================
    def _calcular_g2_pavimento(self, params: dict) -> float:
        gama_pav = self.spin_gama_pavimento.value()
        return params["l_pavimento"] * ((params["h_centro"] + params["h_borda"]) / 2.0) * gama_pav

    def _calcular_g2_repavimentacao(self, params: dict) -> float:
        return params["l_pavimento"] * self.spin_q_repavimentacao.value()

    def _calcular_g2_guarda_rodas(self) -> float:
        return 2.0 * self.spin_area_guarda_rodas.value() * self.spin_gama_c.value()

    def _calcular_g2_passeio(self, params: dict) -> float | None:
        if not params["l_passeio"]:
            return None
        n         = 1 if params["sec"].is_pista_dupla() else 2
        h_passeio = self.spin_gama_h_passeio.value()
        gama_pav  = self.spin_gama_pavimento.value()
        q_gc      = self.spin_q_guarda_corpo.value()
        return n * ((params["l_passeio"] * h_passeio * gama_pav) + q_gc)

    def _calcular_g2_total_bruto(self, params: dict) -> float:
        """Soma bruta de todas as parcelas de g2."""
        g2_pav   = self._calcular_g2_pavimento(params)
        g2_repav = self._calcular_g2_repavimentacao(params)
        g2_gr    = self._calcular_g2_guarda_rodas()
        g2_pas   = self._calcular_g2_passeio(params)
        return g2_pav + g2_repav + g2_gr + (g2_pas if g2_pas is not None else 0.0)

    # =========================================================================
    # Atualização dos painéis HTML
    # =========================================================================
    def _atualizar_html_pavimento(self, ativo: bool = None):
        if ativo is None:
            ativo = self.radio_automatico.isChecked()
        params = self._obter_parametros_base()
        if not params:
            return
        self.html_pavimento.setText(
            gerar_html_pavimento(
                params["l_pavimento"],
                params["h_centro"],
                params["h_borda"],
                self.spin_gama_pavimento.value(),
                ativo=ativo,
            )
        )

    def _atualizar_html_repavimentacao(self, ativo: bool = None):
        if ativo is None:
            ativo = self.radio_automatico.isChecked()
        params = self._obter_parametros_base()
        if not params:
            return
        self.html_repavimentacao.setText(
            gerar_html_repavimentacao(
                params["l_pavimento"],
                self.spin_q_repavimentacao.value(),
                ativo=ativo,
            )
        )

    def _atualizar_html_guarda_rodas(self, ativo: bool = None):
        if ativo is None:
            ativo = self.radio_automatico.isChecked()
        self.html_guarda_rodas.setText(
            gerar_html_guarda_rodas(
                self.spin_area_guarda_rodas.value(),
                self.spin_gama_c.value(),
                ativo=ativo,
            )
        )

    def _atualizar_html_passeio(self, ativo: bool = None):
        if ativo is None:
            ativo = self.radio_automatico.isChecked()
        params = self._obter_parametros_base()
        if not params or not params["l_passeio"]:
            return
        n = 1 if params["sec"].is_pista_dupla() else 2
        self.html_sobrecarga_passeio.setText(
            gerar_html_sobrecarga_passeio(
                params["l_passeio"],
                self.spin_gama_h_passeio.value(),
                self.spin_gama_pavimento.value(),
                self.spin_q_guarda_corpo.value(),
                n,
                ativo=ativo,
            )
        )

    def _atualizar_html_g2_total(self, ativo: bool = None):
        if ativo is None:
            ativo = self.radio_automatico.isChecked()
        params = self._obter_parametros_base()
        if not params:
            return

        g2_pav   = self._calcular_g2_pavimento(params)
        g2_repav = self._calcular_g2_repavimentacao(params)
        g2_gr    = self._calcular_g2_guarda_rodas()
        g2_pas   = self._calcular_g2_passeio(params)
        n_long   = params["n_longarinas"]

        if ativo:
            total_bruto = g2_pav + g2_repav + g2_gr + (g2_pas if g2_pas is not None else 0.0)
            self.g2_valor_calculado = total_bruto / n_long
        else:
            self.g2_valor_calculado = self.doubleSpinBox_g2.value()

        self.html_g2_total.setText(
            gerar_html_g2_total(g2_pav, g2_repav, g2_gr, n_long, g2_pas, ativo=ativo)
        )

    def _atualizar_todos_htmls(self, ativo: bool = None):
        """Atualiza todos os labels HTML de uma só vez."""
        self._atualizar_html_pavimento(ativo)
        self._atualizar_html_repavimentacao(ativo)
        self._atualizar_html_guarda_rodas(ativo)
        self._atualizar_html_passeio(ativo)
        self._atualizar_html_g2_total(ativo)

    # =========================================================================
    # Desenho da seção transversal
    # =========================================================================
    def _renderizar_desenho_secao(self):
        """Desenha a seção transversal da via no painel esquerdo."""
        sec = self.gerenciador.get_secao_transversal()
        if not sec:
            lbl = QLabel("Seção Transversal não definida.")
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.layout_desenho.addWidget(lbl)
            return

        if self.fig_secao:
            plt.close(self.fig_secao)
            self.fig_secao = None

        for i in reversed(range(self.layout_desenho.count())):
            widget = self.layout_desenho.itemAt(i).widget()
            if widget:
                widget.setParent(None)

        config_pers = None
        if sec.classe == "Personalizado":
            config_pers = sec.obter_config_via()

        self.fig_secao = desenhar_sec_transversal(
            classe=sec.classe,
            h_borda=sec.h_borda,
            h_centro=sec.h_centro,
            passeio=sec.passeio if sec.passeio else False,
            config_personalizado=config_pers
        )

        if self.fig_secao:
            self.layout_desenho.addWidget(FigureCanvas(self.fig_secao))
        else:
            lbl = QLabel("Pré-visualização não disponível para esta configuração.")
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.layout_desenho.addWidget(lbl)

    # =========================================================================
    # Mapeamento da estrutura e montagem das ações
    # =========================================================================
    def _obter_tipo_interno(self, texto_visual: str) -> str:
        for chave, interno in MAPA_TIPOS.items():
            if chave in texto_visual:
                return interno
        if "Múltiplos Vãos"       in texto_visual: return "biapoiada"
        if "Biapoiada com Balanço" in texto_visual: return "isostatica_em_balanco"
        if "Contínuo sem Balanço"  in texto_visual: return "hiperestatica_sem_balanco"
        if "Contínuo com Balanço"  in texto_visual: return "hiperestatica_com_balanco"
        return "biapoiada"

    def _mapear_coordenadas_estrutura(
        self, tipo_interno: str, vaos: list, laje_transicao: float
    ) -> tuple[float, float, list, list]:
        if tipo_interno in ("isostatica_em_balanco", "hiperestatica_sem_balanco"):
            soma_vaos = vaos[0] + 2 * vaos[1]
        elif tipo_interno == "hiperestatica_com_balanco":
            soma_vaos = vaos[0] + 2 * vaos[1] + 2 * vaos[2]
        else:
            soma_vaos = sum(vaos)

        soma_lajes  = (2 * laje_transicao) if laje_transicao else 0.0
        total_real  = soma_vaos + soma_lajes
        fator       = max(0.5, total_real / 20.0)
        gap_visual  = (0.60 * fator) + (0.15 * fator)

        x_ini     = laje_transicao if laje_transicao else 0.0
        x_cursor  = x_ini
        pontos_apoio = []
        pontos_meio  = []

        if tipo_interno == "biapoiada":
            for vao in vaos:
                pontos_apoio.extend([x_cursor, x_cursor + vao])
                pontos_meio.append(x_cursor + vao / 2.0)
                x_cursor += vao + gap_visual
            x_fim = x_cursor - gap_visual

        elif tipo_interno == "isostatica_em_balanco":
            v_int, v_bal = vaos[0], vaos[1]
            p0, p1 = x_ini, x_ini + v_bal
            p2, p3 = p1 + v_int, p1 + v_int + v_bal
            pontos_apoio.extend([p1, p2])
            pontos_meio.extend([p0 + v_bal / 2, p1 + v_int / 2, p2 + v_bal / 2])
            x_fim = p3

        elif tipo_interno == "hiperestatica_com_balanco":
            v_c, v_e, v_b = vaos[0], vaos[1], vaos[2]
            p0 = x_ini
            p1, p2, p3 = p0 + v_b, p0 + v_b + v_e, p0 + v_b + v_e + v_c
            p4, p5      = p3 + v_e, p3 + v_e + v_b
            pontos_apoio.extend([p1, p2, p3, p4])
            pontos_meio.extend([
                p0 + v_b / 2, p1 + v_e / 2, p2 + v_c / 2,
                p3 + v_e / 2, p4 + v_b / 2,
            ])
            x_fim = p5

        else:  # hiperestatica_sem_balanco
            v_c, v_e = vaos[0], vaos[1]
            p0 = x_ini
            p1, p2, p3 = p0 + v_e, p0 + v_e + v_c, p0 + v_e + v_c + v_e
            pontos_apoio.extend([p0, p1, p2, p3])
            pontos_meio.extend([p0 + v_e / 2, p1 + v_c / 2, p2 + v_e / 2])
            x_fim = p3

        return x_ini, x_fim, pontos_apoio, pontos_meio

    def _montar_dicionario_acoes(self) -> dict:
        sup           = self.gerenciador.get_superestrutura()
        tipo_interno  = self._obter_tipo_interno(sup.tipo)
        laje_transicao = float(sup.laje_transicao) if sup.laje_transicao else 0.0

        x_ini, x_fim, _, _ = self._mapear_coordenadas_estrutura(
            tipo_interno, sup.vaos, laje_transicao
        )

        acoes = {
            "Carga Concentrada": [],
            "Carga Distribuída": [],
        }

        g2 = round(self.g2_valor_calculado, 2)

        if self.check_transversina.isChecked() and laje_transicao:
            q_aterro    = self.spin_q_aterro.value()
            g2_c_aterro = round(g2 + q_aterro, 2)
            acoes["Carga Distribuída"].append([g2_c_aterro, 0.0, x_ini])
            acoes["Carga Distribuída"].append([g2, x_ini, x_fim])
            acoes["Carga Distribuída"].append([g2_c_aterro, x_fim, x_fim + laje_transicao])
        else:
            # A carga g2 cobre toda a extensão (inclui lajes de transição)
            acoes["Carga Distribuída"].append([g2, 0.0, x_fim + laje_transicao])

        return acoes

    # =========================================================================
    # Desenho da ponte carregada
    # =========================================================================
    def _processar_desenho_ponte(self):
        sup = self.gerenciador.get_superestrutura()
        if not sup:
            QMessageBox.warning(self, "Aviso", "A Superestrutura precisa estar definida.")
            return

        self._atualizar_todos_htmls()

        tipo_interno   = self._obter_tipo_interno(sup.tipo)
        laje_transicao = float(sup.laje_transicao) if sup.laje_transicao else 0.0
        acoes          = self._montar_dicionario_acoes()

        if self.fig_ponte:
            plt.close(self.fig_ponte)
            self.fig_ponte = None

        for i in reversed(range(self.layout_desenho_2.count())):
            widget = self.layout_desenho_2.itemAt(i).widget()
            if widget:
                widget.setParent(None)

        try:
            self.fig_ponte = desenhar_ponte_carregada(
                tipo=tipo_interno,
                vaos=sup.vaos,
                laje_transicao=laje_transicao,
                acoes=acoes,
            )
            self.layout_desenho_2.addWidget(FigureCanvas(self.fig_ponte))
        except Exception as e:
            QMessageBox.critical(self, "Erro de Renderização",
                                 f"Ocorreu um erro ao gerar o DCL da ponte:\n{str(e)}")

    # =========================================================================
    # Cálculo via MEF
    # =========================================================================
    def _processar_calculos(self):
        sup      = self.gerenciador.get_superestrutura()
        sec_sup  = self.gerenciador.get_secao_superestrutura()

        if not sup or not sec_sup:
            QMessageBox.warning(self, "Aviso",
                                "Superestrutura e Seção Transversal da Superestrutura "
                                "precisam estar definidos antes de calcular.")
            return

        self._atualizar_todos_htmls()

        acoes = self._montar_dicionario_acoes()
        modulo_E = 3000.0

        # Fecha figuras antigas
        if self.fig_cortante:
            plt.close(self.fig_cortante)
            self.fig_cortante = None
        if self.fig_momento:
            plt.close(self.fig_momento)
            self.fig_momento = None

        try:
            self.calculadora = CalculadoraElementosFinitos(
                superestrutura=sup,
                secao_superestrutura=sec_sup,
                acoes=acoes,
                modulo_elasticidade=modulo_E,
            )

            self.tabela_reacoes, self.tabela_cortante, self.tabela_momento = (
                self.calculadora.calcular()
            )
            self.fig_cortante = self.calculadora.plotar_cortante()
            self.fig_momento  = self.calculadora.plotar_momento()

            secoes_criticas = {
                "Cortante": self.calculadora._secoes_criticas(self.tabela_cortante, "Cortante"),
                "Momento":  self.calculadora._secoes_criticas(self.tabela_momento, "Momento"),
                "Reações":  self.calculadora._secoes_criticas(self.tabela_reacoes, "Reações"),
            }

            html_resumo = gerar_html_resultados_esforcos_calculos(
                secoes_criticas=secoes_criticas,
                tipo_dado="estatico"
            )
            self.html_resultados_esforcos.setHtml(html_resumo)

            valores_r = [float(linha[2]) for linha in self.tabela_reacoes[1:]]
            valores_v = [float(linha[2]) for linha in self.tabela_cortante[1:]]
            valores_m = [float(linha[2]) for linha in self.tabela_momento[1:]]

            self.valores_limites = {
                "r_max": max(valores_r) if valores_r else 0.0,
                "v_min": min(valores_v) if valores_v else 0.0,
                "v_max": max(valores_v) if valores_v else 0.0,
                "m_min": min(valores_m) if valores_m else 0.0,
                "m_max": max(valores_m) if valores_m else 0.0,
            }

            self.botao_cortante.setEnabled(True)
            self.botao_momento.setEnabled(True)
            self.botao_reacoes.setEnabled(True)

        except Exception as e:
            QMessageBox.critical(self, "Erro no Cálculo",
                                 f"Falha na Análise FEM:\n{str(e)}")

    # =========================================================================
    # Abertura das janelas de resultados detalhados
    # =========================================================================
    def _abrir_janela_cortante(self):
        if self.fig_cortante:
            plt.close(self.fig_cortante)
        self.fig_cortante = self.calculadora.plotar_cortante()

        valores_v = [float(linha[2]) for linha in self.tabela_cortante[1:]]
        v_min, v_max = min(valores_v), max(valores_v)

        janela = LogicaJanelaResultadosEsforcos(
            titulo_janela="Resumo do Esforço Cortante: Sobrecarga",
            titulo_diagrama="Diagrama de Esforço Cortante",
            titulo_tabela="Tabela de Esforço Cortante",
            dados_tabela=self.tabela_cortante,
            figura_matplotlib=self.fig_cortante,
            valores_destaque=[v_min, v_max],
        )
        janela.exec()

    def _abrir_janela_momento(self):
        if self.fig_momento:
            plt.close(self.fig_momento)
        self.fig_momento = self.calculadora.plotar_momento()

        valores_m = [float(linha[2]) for linha in self.tabela_momento[1:]]
        m_min, m_max = min(valores_m), max(valores_m)

        janela = LogicaJanelaResultadosEsforcos(
            titulo_janela="Resumo do Momento Fletor: Sobrecarga",
            titulo_diagrama="Diagrama de Momento Fletor",
            titulo_tabela="Tabela de Momento Fletor",
            dados_tabela=self.tabela_momento,
            figura_matplotlib=self.fig_momento,
            valores_destaque=[m_min, m_max],
        )
        janela.exec()

    def _abrir_janela_reacoes(self):
        valores_r = [float(linha[2]) for linha in self.tabela_reacoes[1:]]
        r_max = max(valores_r)

        janela = LogicaJanelaResultadosReacoes(
            titulo_janela="Resumo das Reações de Apoio: Sobrecarga",
            dados_tabela=self.tabela_reacoes,
            valores_destaque=[r_max],
        )
        janela.exec()

    # =========================================================================
    # Salvamento dos dados
    # =========================================================================
    def _acao_confirmar(self):
        if not (self.tabela_cortante and self.tabela_momento and self.tabela_reacoes):
            QMessageBox.warning(self, "Aviso",
                                "Realize os cálculos (botão Calcular) antes de confirmar.")
            return

        self.gerenciador.definir_esforco(
            nome="sobrecarga",
            cortante=self.tabela_cortante,
            momento=self.tabela_momento,
            reacoes=self.tabela_reacoes,
            valores_limites=self.valores_limites
        )
        self.accept()

    # =========================================================================
    # Manual do usuário
    # =========================================================================
    def abrir_manual(self):
        """
        Abre o manual do software no PDFViewer na seção de análise da
        sobrecarga permanente (g2).

        Navega diretamente para a página 59 do manual (índice 58 em base 0,
        pois o PyMuPDF (fitz) indexa páginas a partir de zero).
        """
        pdf_path = resource_path(os.path.join("assets", "Manual Girder25 Dark.pdf"))
        viewer = PDFViewer(pdf_path, "Manual: ANÁLISE DA SOBRECARGA PERMANENTE (𝒈𝟐)")
        viewer.display_page(58)   # página 59 do manual → índice 58
        viewer.exec()