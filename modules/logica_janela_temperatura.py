# ============================================================================
# Girder25 - logica_janela_temperatura.py
# Autor: Fábio Henrique Sampaio Júnior
# Controlador da análise do gradiente térmico (efeito de temperatura).
# ============================================================================

import os
import matplotlib.pyplot as plt
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas

from PyQt6.QtWidgets import QDialog, QMessageBox, QVBoxLayout
from PyQt6.QtCore import Qt

from ui.janela_temperatura import Ui_janela_temperatura

from modules.funcoes_janela_temperatura import (
    obter_gradiente_ponte,
    desenhar_secao,
    calcular_gradiente_equivalente,
    calcular_modulo_elasticidade,
    gerar_html_parametros_gradiente,
    gerar_html_gradiente_termico,
    gerar_html_modulo_elasticidade,
    gerar_memorial_gradiente_ponte,
)
from modules.Calculadora_Gradiente_Termico import CalculadoraGradienteTermico
from modules.logica_resultados_temperatura import (
    LogicaJanelaResultadosEsforcos,
    LogicaJanelaResultadosReacoes,
)
from modules.gerar_html import gerar_html_resultados_esforcos_calculos
from modules.logica_janela_memorial import LogicaJanelaMemorial
from modules.visualizador_pdf import PDFViewer
from modules.utils import resource_path


# Tipos estruturais que exigem análise de temperatura (hiperestáticos)
_TIPOS_VALIDOS = {
    "Hiperestática: Vão Contínuo sem Balanço",
    "Hiperestática: Vão Contínuo com Balanço",
}


class LogicaJanelaTemperatura(QDialog, Ui_janela_temperatura):
    """
    Diálogo para análise do gradiente térmico conforme NBR 7187:2021.
    Calcula o ΔT equivalente, o módulo de elasticidade e executa a análise
    MEF para obtenção dos esforços e reações devidos à temperatura.
    """

    def __init__(self, gerenciador):
        super().__init__()
        self.setupUi(self)
        self.gerenciador = gerenciador

        self.sup       = gerenciador.get_superestrutura()
        self.sec       = gerenciador.get_secao_transversal()
        self.sec_super = gerenciador.get_secao_superestrutura()

        self._h_total_cm: float = self.sec_super.parametros_geometricos.get("h", 0.0)
        self._espessura_revest_cm: float = (
            self.sec.h_borda + self.sec.h_centro
        ) / 2.0
        self._largura_colaborante: float = self.sec_super.largura_colaborante
        self._h_laje: float = self.sec_super.h_laje
        self._dados_secao: dict = self.sec_super.dados

        # Gradiente térmico da ponte (NBR 7187:2021)
        self._gradiente_ponte: dict = obter_gradiente_ponte(
            self._h_total_cm, self._espessura_revest_cm
        )

        # Valores calculados (ΔT e módulo de elasticidade)
        self._deltat_calculado: float = 0.0
        self._E_calculado:      float = 0.0

        # Figuras do Matplotlib
        self._fig_secao:    object = None
        self._fig_cortante: object = None
        self._fig_momento:  object = None

        # Calculadora de gradiente térmico
        self._calculadora: CalculadoraGradienteTermico = None

        # Tabelas de esforços e reações
        self.tabela_reacoes:  list = []
        self.tabela_cortante: list = []
        self.tabela_momento:  list = []
        self.valores_limites = {}

        # Layout para o diagrama da seção com gradiente
        self._layout_frame_gradiente = QVBoxLayout(self.frame_gradiente)
        self._layout_frame_gradiente.setContentsMargins(0, 0, 0, 0)

        self._configurar_interface()
        self._configurar_sinais()
        self._inicializar_estados()
        self._renderizar_tudo()

    # -------------------------------------------------------------------------
    # Gerenciamento da janela
    # -------------------------------------------------------------------------
    def closeEvent(self, event):
        """Libera todas as figuras do Matplotlib ao fechar o diálogo."""
        for fig in (self._fig_secao, self._fig_cortante, self._fig_momento):
            if fig:
                plt.close(fig)
        self._fig_secao = None
        self._fig_cortante = None
        self._fig_momento = None
        super().closeEvent(event)

    # -------------------------------------------------------------------------
    # Configuração inicial da interface
    # -------------------------------------------------------------------------
    def _configurar_interface(self):
        """Aplica limites, passos e valores padrão aos spinboxes."""
        self.spin_deltat.setRange(1.0, 30.0)
        self.spin_deltat.setSingleStep(0.5)
        self.spin_deltat.setValue(12.0)
        self.spin_deltat.setSuffix(" °C")

        self.spin_e.setRange(15_000.0, 45_000.0)
        self.spin_e.setSingleStep(500.0)
        self.spin_e.setValue(27_000.0)
        self.spin_e.setSuffix(" MPa")
        self.spin_e.setDecimals(0)

        self.spin_alpha.setRange(0.7, 1.2)
        self.spin_alpha.setSingleStep(0.01)
        self.spin_alpha.setValue(1.0)
        self.spin_alpha.setSuffix(" × 10⁻⁵ /°C")
        self.spin_alpha.setDecimals(2)

        self.combo_classe_concreto.setCurrentIndex(2)

        self.html_resultados_esforcos.setPlainText("Aguardando Cálculos")
        self.botao_cortante.setEnabled(False)
        self.botao_momento.setEnabled(False)
        self.botao_reacoes.setEnabled(False)

    def _configurar_sinais(self):
        """Conecta os sinais dos widgets às funções de tratamento."""
        self.deltat_automatico.toggled.connect(self._on_toggle_deltat)
        self.e_automatico.toggled.connect(self._on_toggle_e)

        self.combo_classe_concreto.currentIndexChanged.connect(
            self._atualizar_modulo_elasticidade
        )
        self.combo_tipo_agregado.currentIndexChanged.connect(
            self._atualizar_modulo_elasticidade
        )

        self.calcular.clicked.connect(self._processar_calculos)

        self.botao_cortante.clicked.connect(self._abrir_janela_cortante)
        self.botao_momento.clicked.connect(self._abrir_janela_momento)
        self.botao_reacoes.clicked.connect(self._abrir_janela_reacoes)

        self.memorial_temp.clicked.connect(self._abrir_memorial_gradiente)

        self.cancelar.clicked.connect(self.reject)
        self.confirmar.clicked.connect(self._acao_confirmar)

        # Manual do usuário
        self.manual.clicked.connect(self.abrir_manual)

    def _inicializar_estados(self):
        """Define os estados iniciais dos rádios (automático)."""
        self.deltat_automatico.setChecked(True)
        self._on_toggle_deltat(True)

        self.e_automatico.setChecked(True)
        self._on_toggle_e(True)

    def _renderizar_tudo(self):
        """Executa a renderização inicial da seção e atualiza os HTMLs."""
        self._renderizar_secao_e_gradiente()
        self._atualizar_html_parametros_gradiente()
        self._atualizar_html_gradiente_termico()
        self._atualizar_modulo_elasticidade()

    # -------------------------------------------------------------------------
    # Desenho da seção com gradiente térmico
    # -------------------------------------------------------------------------
    def _renderizar_secao_e_gradiente(self):
        """Desenha a seção transversal com a distribuição de temperatura."""
        if self._fig_secao:
            plt.close(self._fig_secao)
            self._fig_secao = None

        for i in reversed(range(self._layout_frame_gradiente.count())):
            widget = self._layout_frame_gradiente.itemAt(i).widget()
            if widget:
                widget.setParent(None)

        try:
            self._fig_secao = desenhar_secao(
                dados=self._dados_secao,
                exibir_cotas=True,
                h_laje=self._h_laje,
                largura_colaborante=self._largura_colaborante,
                gradiente=self._gradiente_ponte,
            )
            canvas = FigureCanvas(self._fig_secao)
            self._layout_frame_gradiente.addWidget(
                canvas, alignment=Qt.AlignmentFlag.AlignCenter
            )
        except Exception as e:
            QMessageBox.critical(
                self,
                "Erro na Seção",
                f"Não foi possível renderizar a seção:\n{str(e)}",
            )

    # -------------------------------------------------------------------------
    # Atualização dos painéis HTML
    # -------------------------------------------------------------------------
    def _atualizar_html_parametros_gradiente(self):
        """Atualiza o painel com os parâmetros do gradiente térmico."""
        html = gerar_html_parametros_gradiente(
            h_total=self._h_total_cm,
            espessura_media=self._espessura_revest_cm,
            gradiente_ponte=self._gradiente_ponte,
        )
        self.html_parametros_gradiente.setText(html)

    def _atualizar_html_gradiente_termico(self):
        """Calcula e exibe o gradiente equivalente e o memorial resumido."""
        try:
            resultados, memorial_texto = calcular_gradiente_equivalente(
                dados=self._dados_secao,
                gradiente=self._gradiente_ponte,
                h_laje=self._h_laje,
                largura_colaborante=self._largura_colaborante,
            )
            self._deltat_calculado = resultados.get("Delta_T_eq", 0.0)

            html = gerar_html_gradiente_termico(
                resultados,
                memorial_texto,
                ativo=self.deltat_automatico.isChecked()
            )
            self.html_gradiente_termico.setText(html)
        except Exception as e:
            QMessageBox.critical(
                self,
                "Erro no Gradiente",
                f"Não foi possível calcular o gradiente equivalente:\n{str(e)}",
            )

    def _atualizar_modulo_elasticidade(self):
        """Atualiza o painel do módulo de elasticidade conforme classe e agregado."""
        classe_concreto = self.combo_classe_concreto.currentText()
        tipo_agregado   = self.combo_tipo_agregado.currentText()

        res = calcular_modulo_elasticidade(classe_concreto, tipo_agregado)
        self._E_calculado = res["E_cs"]

        html = gerar_html_modulo_elasticidade(
            res,
            ativo=self.e_automatico.isChecked()
        )
        self.html_modulo_elasticidade.setText(html)

    # -------------------------------------------------------------------------
    # Alternância entre automático e manual (ΔT e E)
    # -------------------------------------------------------------------------
    def _on_toggle_deltat(self, automatico: bool):
        self.html_gradiente_termico.setEnabled(automatico)
        self.label_deltat_manual.setEnabled(not automatico)
        self.spin_deltat.setEnabled(not automatico)
        self._atualizar_html_gradiente_termico()

    def _on_toggle_e(self, automatico: bool):
        self.html_modulo_elasticidade.setEnabled(automatico)
        self.combo_classe_concreto.setEnabled(automatico)
        self.combo_tipo_agregado.setEnabled(automatico)
        self.label_3.setEnabled(automatico)
        self.label_4.setEnabled(automatico)

        self.label_e_manual.setEnabled(not automatico)
        self.spin_e.setEnabled(not automatico)

        self._atualizar_modulo_elasticidade()

    # -------------------------------------------------------------------------
    # Montagem dos parâmetros para a calculadora
    # -------------------------------------------------------------------------
    def _montar_parametros_temperatura(self) -> dict:
        """Retorna dicionário com ΔT, E e α conforme o modo selecionado."""
        if self.deltat_automatico.isChecked():
            deltat = self._deltat_calculado
        else:
            deltat = self.spin_deltat.value()

        if self.e_automatico.isChecked():
            E = self._E_calculado
        else:
            E = self.spin_e.value()

        alpha = self.spin_alpha.value() * 1e-5

        return {
            "deltat": deltat,
            "E":      E,
            "alpha":  alpha,
        }

    # -------------------------------------------------------------------------
    # Cálculo via MEF dos esforços térmicos
    # -------------------------------------------------------------------------
    def _processar_calculos(self):
        """Executa a análise MEF para o carregamento térmico."""
        if not self.sup or not self.sec_super:
            QMessageBox.warning(
                self,
                "Aviso",
                "Superestrutura e Seção da Superestrutura precisam estar definidas.",
            )
            return

        # Fecha figuras anteriores
        if self._fig_cortante:
            plt.close(self._fig_cortante)
            self._fig_cortante = None
        if self._fig_momento:
            plt.close(self._fig_momento)
            self._fig_momento = None

        parametros_temperatura = self._montar_parametros_temperatura()

        try:
            self._calculadora = CalculadoraGradienteTermico(
                superestrutura=self.sup,
                secao_superestrutura=self.sec_super,
                parametros_temperatura=parametros_temperatura,
            )

            (
                self.tabela_reacoes,
                self.tabela_cortante,
                self.tabela_momento,
            ) = self._calculadora.calcular()

            self._fig_cortante = self._calculadora.plotar_cortante()
            self._fig_momento  = self._calculadora.plotar_momento()

            secoes_criticas = {
                "Cortante": self._calculadora._secoes_criticas(self.tabela_cortante, "Cortante"),
                "Momento":  self._calculadora._secoes_criticas(self.tabela_momento, "Momento"),
                "Reações":  self._calculadora._secoes_criticas(self.tabela_reacoes, "Reações"),
            }

            html_resumo = gerar_html_resultados_esforcos_calculos(
                secoes_criticas=secoes_criticas,
                tipo_dado="estatico"
            )
            self.html_resultados_esforcos.setHtml(html_resumo)

            valores_r = [float(linha[2]) for linha in self.tabela_reacoes[1:]]
            valores_v = [float(linha[2]) for linha in self.tabela_cortante[1:]]
            valores_m = [float(linha[2]) for linha in self.tabela_momento[1:]]

            r_max = max(valores_r) if valores_r else 0.0
            v_min = min(valores_v) if valores_v else 0.0
            v_max = max(valores_v) if valores_v else 0.0
            m_min = min(valores_m) if valores_m else 0.0
            m_max = max(valores_m) if valores_m else 0.0

            self.valores_limites = {
                "r_max": r_max,
                "v_min": v_min,
                "v_max": v_max,
                "m_min": m_min,
                "m_max": m_max
            }

            self.botao_cortante.setEnabled(True)
            self.botao_momento.setEnabled(True)
            self.botao_reacoes.setEnabled(True)

        except Exception as e:
            QMessageBox.critical(
                self,
                "Erro no Cálculo",
                f"Falha na Análise MEF Térmica:\n{str(e)}",
            )

    # -------------------------------------------------------------------------
    # Abertura das janelas de resultados detalhados
    # -------------------------------------------------------------------------
    def _abrir_janela_cortante(self):
        if self._fig_cortante:
            plt.close(self._fig_cortante)
        self._fig_cortante = self._calculadora.plotar_cortante()

        valores_v = [float(linha[2]) for linha in self.tabela_cortante[1:]]
        v_min, v_max = min(valores_v), max(valores_v)

        janela = LogicaJanelaResultadosEsforcos(
            titulo_janela="Resumo do Esforço Cortante: Gradiente Térmico",
            titulo_diagrama="Diagrama de Esforço Cortante — Temperatura",
            titulo_tabela="Tabela de Esforço Cortante",
            dados_tabela=self.tabela_cortante,
            figura_matplotlib=self._fig_cortante,
            valores_destaque=[v_min, v_max],
        )
        janela.exec()

    def _abrir_janela_momento(self):
        if self._fig_momento:
            plt.close(self._fig_momento)
        self._fig_momento = self._calculadora.plotar_momento()

        valores_m = [float(linha[2]) for linha in self.tabela_momento[1:]]
        m_min, m_max = min(valores_m), max(valores_m)

        janela = LogicaJanelaResultadosEsforcos(
            titulo_janela="Resumo do Momento Fletor: Gradiente Térmico",
            titulo_diagrama="Diagrama de Momento Fletor — Temperatura",
            titulo_tabela="Tabela de Momento Fletor",
            dados_tabela=self.tabela_momento,
            figura_matplotlib=self._fig_momento,
            valores_destaque=[m_min, m_max],
        )
        janela.exec()

    def _abrir_janela_reacoes(self):
        valores_r = [float(linha[2]) for linha in self.tabela_reacoes[1:]]
        r_max = max(valores_r) if valores_r else 0.0

        janela = LogicaJanelaResultadosReacoes(
            titulo_janela="Resumo das Reações de Apoio: Gradiente Térmico",
            dados_tabela=self.tabela_reacoes,
            valores_destaque=[r_max],
        )
        janela.exec()

    # -------------------------------------------------------------------------
    # Memorial do gradiente térmico
    # -------------------------------------------------------------------------
    def _abrir_memorial_gradiente(self):
        """
        Gera e exibe o memorial completo do gradiente térmico da ponte
        conforme a NBR 7187:2021.
        """
        try:
            html_memorial = gerar_memorial_gradiente_ponte(
                self._h_total_cm,
                self._espessura_revest_cm
            )
            dlg = LogicaJanelaMemorial(
                "Memorial Gradiente Térmico de Ponte (NBR 7187:2021)",
                html_memorial,
                parent=self
            )
            dlg.exec()
        except Exception as e:
            QMessageBox.critical(
                self,
                "Erro ao Gerar Memorial",
                f"Não foi possível gerar o memorial do gradiente térmico:\n{str(e)}"
            )

    # -------------------------------------------------------------------------
    # Salvamento dos dados
    # -------------------------------------------------------------------------
    def _acao_confirmar(self):
        if (
            not self.tabela_cortante
            or not self.tabela_momento
            or not self.tabela_reacoes
        ):
            QMessageBox.warning(
                self,
                "Aviso",
                "Realize os cálculos antes de confirmar.",
            )
            return

        self.gerenciador.definir_esforco(
            nome="temperatura",
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
        Abre o manual do software no PDFViewer na seção de análise do
        gradiente térmico.

        Navega diretamente para a página 61 do manual (índice 61 em base 0,
        pois o PyMuPDF (fitz) indexa páginas a partir de zero).
        """
        pdf_path = resource_path(os.path.join("assets", "Manual Girder25 Dark.pdf"))
        viewer = PDFViewer(pdf_path, "Manual: ANÁLISE DO GRADIENTE TÉRMICO")
        viewer.display_page(61)   # página 61 do manual → índice 61
        viewer.exec()