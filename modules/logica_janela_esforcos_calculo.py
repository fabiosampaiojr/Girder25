# ============================================================================
# Girder25 - logica_janela_esforcos_calculo.py
# Autor: Fábio Henrique Sampaio Júnior
# Controlador da envoltória de esforços de cálculo (Sd).
# ============================================================================

import os
from PyQt6.QtWidgets import QDialog, QMessageBox, QButtonGroup
import matplotlib.pyplot as plt

from ui.janela_esforcos_calculo import Ui_janela_esforcos_calculo
from modules.Calculadora_Esforcos import CalculadoraEsforcos
from modules.logica_resultados_esforcos_calculo import (
    LogicaJanelaResultadosEnvoltoria,
    LogicaJanelaResultadosReacoesEnvoltoria
)
from modules.gerar_html import (
    gerar_html_coeficientes,
    gerar_html_resultados_esforcos_calculos
)
from modules.visualizador_pdf import PDFViewer
from modules.utils import resource_path


class LogicaJanelaEsforcosCalculo(QDialog, Ui_janela_esforcos_calculo):
    """
    Diálogo para combinação dos esforços (peso próprio, sobrecarga,
    temperatura e carga móvel) e geração das envoltórias de cálculo
    nos estados limites último (ELU) e de serviço (ELS).
    """

    def __init__(self, gerenciador):
        super().__init__()
        self.setupUi(self)
        self.gerenciador = gerenciador

        self.calculadora = None
        self.resultados_calculo = {}  # Armazena os resultados para ELU e ELS
        self.coeficientes_calculo = {}

        self.configurar_interface()
        self.configurar_sinais()
        self.atualizar_estado_coeficientes()
        self.atualizar_html_coeficientes()

        # Manual do usuário
        self.manual.clicked.connect(self.abrir_manual)

    def configurar_interface(self):
        """Aplica limites, valores padrão e estados iniciais aos controles."""
        self.spin_gama_g.setRange(1.0, 2.0)
        self.spin_gama_g.setValue(1.35)
        self.spin_gama_g.setSingleStep(0.05)

        self.spin_gama_q.setRange(1.0, 2.0)
        self.spin_gama_q.setValue(1.50)
        self.spin_gama_q.setSingleStep(0.05)

        self.spin_gama_temp_q.setRange(1.0, 1.5)
        self.spin_gama_temp_q.setValue(1.20)
        self.spin_gama_temp_q.setSingleStep(0.05)

        self.spin_psi0.setRange(0.1, 1.0)
        self.spin_psi0.setValue(0.60)
        self.spin_psi0.setSingleStep(0.05)

        self.spin_psi1.setRange(0.1, 1.0)
        self.spin_psi1.setValue(0.50)
        self.spin_psi1.setSingleStep(0.05)

        self.spin_psi2.setRange(0.1, 1.0)
        self.spin_psi2.setValue(0.30)
        self.spin_psi2.setSingleStep(0.05)

        self.radio_automatico.setChecked(True)
        self.radio_elu.setChecked(True)

        # Grupo de exclusividade para ELU/ELS
        self.grupo_estado_limite = QButtonGroup(self)
        self.grupo_estado_limite.addButton(self.radio_elu)
        self.grupo_estado_limite.addButton(self.radio_els)
        self.grupo_estado_limite.setExclusive(True)

        self.html_resultados_esforcos_calculos.setPlainText("Aguardando Cálculos")
        self.botao_cortante.setEnabled(False)
        self.botao_momento.setEnabled(False)
        self.botao_reacoes.setEnabled(False)
        self.radio_elu.setEnabled(False)
        self.radio_els.setEnabled(False)

    def configurar_sinais(self):
        """Conecta os sinais dos widgets às funções de tratamento."""
        self.radio_automatico.toggled.connect(self.atualizar_estado_coeficientes)
        self.radio_personalizado.toggled.connect(self.atualizar_estado_coeficientes)
        self.radio_elu.toggled.connect(self.atualizar_resumo_resultados)
        self.radio_els.toggled.connect(self.atualizar_resumo_resultados)

        self.spin_gama_g.valueChanged.connect(self.montar_dicionario_coeficientes)
        self.spin_gama_q.valueChanged.connect(self.montar_dicionario_coeficientes)
        self.spin_gama_temp_q.valueChanged.connect(self.montar_dicionario_coeficientes)
        self.spin_psi0.valueChanged.connect(self.montar_dicionario_coeficientes)
        self.spin_psi1.valueChanged.connect(self.montar_dicionario_coeficientes)
        self.spin_psi2.valueChanged.connect(self.montar_dicionario_coeficientes)

        self.calcular.clicked.connect(self.processar_calculos)
        self.botao_cortante.clicked.connect(self.abrir_janela_cortante)
        self.botao_momento.clicked.connect(self.abrir_janela_momento)
        self.botao_reacoes.clicked.connect(self.abrir_janela_reacoes)
        self.cancelar.clicked.connect(self.reject)
        self.confirmar.clicked.connect(self.acao_confirmar)

    def atualizar_estado_coeficientes(self):
        """Habilita/desabilita os spinboxes conforme modo automático/personalizado."""
        is_personalizado = self.radio_personalizado.isChecked()
        self.spin_gama_g.setEnabled(is_personalizado)
        self.spin_gama_q.setEnabled(is_personalizado)
        self.spin_gama_temp_q.setEnabled(is_personalizado)
        self.spin_psi0.setEnabled(is_personalizado)
        self.spin_psi1.setEnabled(is_personalizado)
        self.spin_psi2.setEnabled(is_personalizado)
        self.atualizar_html_coeficientes()
        self.montar_dicionario_coeficientes()

    def atualizar_html_coeficientes(self):
        """Atualiza os painéis HTML com os coeficientes normativos ou personalizados."""
        criterio = "normativo" if self.radio_automatico.isChecked() else "automatico"
        htmls = gerar_html_coeficientes(criterio=criterio)
        self.html_normativo.setText(htmls.get("html_normativo", ""))
        self.html_personalizado.setText(htmls.get("html_personalizado", ""))

    def montar_dicionario_coeficientes(self):
        """
        Atualiza o dicionário de coeficientes conforme o modo selecionado
        (normativo ou personalizado).
        """
        if self.radio_automatico.isChecked():
            self.coeficientes_calculo = {
                "gama_g": 1.35, "gama_q": 1.50, "gama_temp_q": 1.20,
                "psi0": 0.60, "psi1": 0.50, "psi2": 0.30
            }
        else:
            self.coeficientes_calculo = {
                "gama_g": self.spin_gama_g.value(),
                "gama_q": self.spin_gama_q.value(),
                "gama_temp_q": self.spin_gama_temp_q.value(),
                "psi0": self.spin_psi0.value(),
                "psi1": self.spin_psi1.value(),
                "psi2": self.spin_psi2.value()
            }

    def processar_calculos(self):
        """Executa a combinação de esforços e gera as envoltórias."""
        esf_pp = self.gerenciador.get_esforco("peso_proprio")
        esf_sp = self.gerenciador.get_esforco("sobrecarga")
        esf_cm = self.gerenciador.get_esforco("carga_movel")

        if not (esf_pp and esf_sp and esf_cm):
            QMessageBox.critical(
                self, "Erro",
                "Faltam objetos de esforços (PP, SC ou CM) para o cálculo."
            )
            return

        esf_temp = self.gerenciador.get_esforco("temperatura")

        try:
            self.calculadora = CalculadoraEsforcos(
                peso_proprio=esf_pp,
                sobrecarga=esf_sp,
                carga_movel=esf_cm,
                coeficientes_calculo=self.coeficientes_calculo,
                temperatura=esf_temp
            )

            self.resultados_calculo = self.calculadora.calcular()

            self.radio_elu.setEnabled(True)
            self.radio_els.setEnabled(True)
            self.radio_elu.setChecked(True)

            self.botao_cortante.setEnabled(True)
            self.botao_momento.setEnabled(True)
            self.botao_reacoes.setEnabled(True)
            self.atualizar_resumo_resultados()

        except Exception as e:
            QMessageBox.critical(
                self, "Erro de Cálculo",
                f"Falha ao gerar a envoltória:\n{str(e)}"
            )

    def atualizar_resumo_resultados(self):
        """Exibe o resumo HTML das seções críticas para ELU ou ELS."""
        if not self.resultados_calculo:
            return

        estado_atual = "ELU" if self.radio_elu.isChecked() else "ELS"

        if estado_atual in self.resultados_calculo:
            secoes_criticas = self.resultados_calculo[estado_atual].get("Seções Críticas", {})
            html_resumo = gerar_html_resultados_esforcos_calculos(
                secoes_criticas=secoes_criticas,
                tipo_dado="calculo"
            )
            self.html_resultados_esforcos_calculos.setHtml(html_resumo)

    def obter_estado_atual(self) -> str:
        """Retorna 'ELU' ou 'ELS' conforme o rádio selecionado."""
        return "ELU" if self.radio_elu.isChecked() else "ELS"

    # -------------------------------------------------------------------------
    # Abertura das janelas de detalhamento
    # -------------------------------------------------------------------------
    def abrir_janela_cortante(self):
        if not self.resultados_calculo or not self.calculadora:
            return

        estado = self.obter_estado_atual()
        dados_estado = self.resultados_calculo[estado]
        tabela = dados_estado["Cortante"]
        secoes_criticas_estado = dados_estado["Seções Críticas"]
        secoes_criticas_cortante = secoes_criticas_estado["Cortante"]
        figura = self.calculadora.plotar_envoltoria(estado, "Cortante")

        min_global = secoes_criticas_cortante["Mínimo"][1]
        max_global = secoes_criticas_cortante["Máximo"][2]

        janela = LogicaJanelaResultadosEnvoltoria(
            titulo_janela=f"Envoltória de Cortante ({estado})",
            titulo_diagrama="Diagrama de Esforço Cortante",
            titulo_tabela="Tabela de Envoltória (Cortante)",
            dados_tabela=tabela,
            figura_matplotlib=figura,
            valores_destaque=[min_global, max_global],
            secoes_criticas=secoes_criticas_estado,
            tipo_esforco="Cortante"
        )
        janela.exec()

    def abrir_janela_momento(self):
        if not self.resultados_calculo or not self.calculadora:
            return

        estado = self.obter_estado_atual()
        dados_estado = self.resultados_calculo[estado]
        tabela = dados_estado["Momento"]
        secoes_criticas_estado = dados_estado["Seções Críticas"]
        secoes_criticas_momento = secoes_criticas_estado["Momento"]
        figura = self.calculadora.plotar_envoltoria(estado, "Momento")

        min_global = secoes_criticas_momento["Mínimo"][1]
        max_global = secoes_criticas_momento["Máximo"][2]

        janela = LogicaJanelaResultadosEnvoltoria(
            titulo_janela=f"Envoltória de Momento ({estado})",
            titulo_diagrama="Diagrama de Momento Fletor",
            titulo_tabela="Tabela de Envoltória (Momento)",
            dados_tabela=tabela,
            figura_matplotlib=figura,
            valores_destaque=[min_global, max_global],
            secoes_criticas=secoes_criticas_estado,
            tipo_esforco="Momento"
        )
        janela.exec()

    def abrir_janela_reacoes(self):
        if not self.resultados_calculo or not self.calculadora:
            return

        estado = self.obter_estado_atual()
        dados_estado = self.resultados_calculo[estado]
        tabela = dados_estado["Reações"]
        secoes_criticas_estado = dados_estado["Seções Críticas"]
        secoes_criticas_reacoes = secoes_criticas_estado["Reações"]

        min_global = secoes_criticas_reacoes["Mínimo"][1]
        max_global = secoes_criticas_reacoes["Máximo"][2]

        janela = LogicaJanelaResultadosReacoesEnvoltoria(
            titulo_janela=f"Envoltória de Reações de Apoio ({estado})",
            dados_tabela=tabela,
            valores_destaque=[min_global, max_global],
            secoes_criticas=secoes_criticas_estado
        )
        janela.exec()

    def acao_confirmar(self):
        """Salva os resultados no gerenciador e fecha o diálogo."""
        if not self.resultados_calculo:
            QMessageBox.warning(
                self, "Aviso",
                "Realize os cálculos de Envoltória antes de confirmar."
            )
            return

        self.gerenciador.definir_esforcos_calculo(self.resultados_calculo)
        self.accept()

    # =========================================================================
    # Manual do usuário
    # =========================================================================
    def abrir_manual(self):
        """
        Abre o manual do software no PDFViewer na seção de esforços de cálculo (Sd).

        Navega diretamente para a página 68 do manual (índice 67 em base 0,
        pois o PyMuPDF (fitz) indexa páginas a partir de zero).
        """
        pdf_path = resource_path(os.path.join("assets", "Manual Girder25 Dark.pdf"))
        viewer = PDFViewer(pdf_path, "Manual: ESFORÇOS DE CÁLCULO (𝑺𝒅)")
        viewer.display_page(67)   # página 68 do manual → índice 67
        viewer.exec()