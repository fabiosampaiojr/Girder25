# ============================================================================
# Girder25 - logica_janela_peso_proprio.py
# Autor: Fábio Henrique Sampaio Júnior
# Controlador da análise das cargas de peso próprio (g1).
# ============================================================================

import os
from PyQt6.QtWidgets import (
    QDialog, QMessageBox, QVBoxLayout, QLabel, QButtonGroup
)
from PyQt6.QtCore import Qt
import matplotlib.pyplot as plt
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas

from ui.janela_peso_proprio import Ui_janela_peso_proprio
from modules.funcoes_sec_super import desenhar_sec_transversal_completa
from modules.gerar_html import (
    gerar_html_calculo_area,
    gerar_html_carga_g1,
    gerar_html_resultados_esforcos_calculos,
)
from modules.desenho_ponte_carregada import desenhar_ponte_carregada
from modules.Calculadora_Elementos_Finitos import CalculadoraElementosFinitos
from modules.logica_resultados_peso_proprio import (
    LogicaJanelaResultadosEsforcos,
    LogicaJanelaResultadosReacoes,
)
from modules.visualizador_pdf import PDFViewer
from modules.utils import resource_path
import traceback

# Mapeamento entre texto da combo e chave interna de tipo estrutural
MAPA_TIPOS = {
    "Isostática: Múltiplos Vãos Biapoioados": "biapoiada",
    "Isostática: Biapoiada com Balanço": "isostatica_em_balanco",
    "Hiperestática: Vão Contínuo sem Balanço": "hiperestatica_sem_balanco",
    "Hiperestática: Vão Contínuo com Balanço": "hiperestatica_com_balanco"
}


class LogicaJanelaPesoProprio(QDialog, Ui_janela_peso_proprio):
    """
    Diálogo para definição e análise das cargas de peso próprio (g1).
    Permite cálculo automático a partir da seção ou entrada manual,
    exibe diagramas de esforços e reações via MEF.
    """

    def __init__(self, gerenciador):
        super().__init__()
        self.setupUi(self)
        self.gerenciador = gerenciador

        # Figuras do Matplotlib
        self.fig_secao = None
        self.fig_ponte = None
        self.fig_cortante = None
        self.fig_momento = None

        # Calculadora MEF
        self.calculadora = None

        # Valor efetivo de g1 (kN/m por longarina)
        self.g1_valor_calculado = 0.0

        # Tabelas de resultados
        self.tabela_reacoes = []
        self.tabela_cortante = []
        self.tabela_momento = []

        # Valores extremos (r_max, v_min, v_max, m_min, m_max)
        self.valores_limites = {}

        # Layouts das áreas de desenho
        self.layout_desenho = QVBoxLayout(self.desenho)
        self.layout_desenho_2 = QVBoxLayout(self.desenho_2)

        # Grupo de exclusividade entre rádios automático/manual
        self.grupo_modo_g1 = QButtonGroup(self)
        self.grupo_modo_g1.addButton(self.radio_automatico)
        self.grupo_modo_g1.addButton(self.radio_manual)

        self.configurar_interface()
        self.configurar_sinais()
        self.verificar_estados_iniciais()

        self.renderizar_desenho_secao()
        self.atualizar_calculos_html()

        # Inicia no modo automático
        self.alternar_modo_g1(True)

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
    def configurar_interface(self):
        """Aplica limites, passos e valores padrão aos controles."""
        self.spin_gama_c.setRange(20.0, 30.0)
        self.spin_gama_c.setSingleStep(0.5)
        self.spin_gama_c.setValue(25.0)
        self.spin_gama_c.setSuffix(" kN/m³")

        self.spin_p_transversina.setRange(5.0, 2000.0)
        self.spin_p_transversina.setSingleStep(0.5)
        self.spin_p_transversina.setValue(30.0)
        self.spin_p_transversina.setSuffix(" kN")

        self.spin_p_extremidade.setRange(1.0, 2000.0)
        self.spin_p_extremidade.setSingleStep(0.5)
        self.spin_p_extremidade.setValue(30.0)
        self.spin_p_extremidade.setSuffix(" kN")

        self.spin_g_placa.setRange(1.0, 2000.0)
        self.spin_g_placa.setValue(30.0)
        self.spin_g_placa.setSuffix(" kN/m")

        lbl_aguardando = QLabel("Aguardando Geração do Desenho")
        lbl_aguardando.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.layout_desenho_2.addWidget(lbl_aguardando)

        self.html_resultados_esforcos.setPlainText("Aguardando Cálculos")
        self.botao_cortante.setEnabled(False)
        self.botao_momento.setEnabled(False)
        self.botao_reacoes.setEnabled(False)

        self.doubleSpinBox_g1.setRange(0.01, 1000.0)
        self.doubleSpinBox_g1.setSingleStep(0.5)
        self.doubleSpinBox_g1.setDecimals(2)
        self.doubleSpinBox_g1.setSuffix(" kN/m")
        self.doubleSpinBox_g1.setEnabled(False)
        self.doubleSpinBox_g1.clear()
        self.doubleSpinBox_g1.lineEdit().setPlaceholderText("")

        self.radio_automatico.setChecked(True)

    def configurar_sinais(self):
        """Conecta os sinais dos widgets às funções de tratamento."""
        self.check_transversina.toggled.connect(self.toggle_transversina)
        self.check_elementos_extremidade.toggled.connect(self.toggle_extremidade)
        self.spin_gama_c.valueChanged.connect(self.atualizar_calculos_html)
        self.atualizar.clicked.connect(self.processar_desenho_ponte)
        self.calcular.clicked.connect(self.processar_calculos)
        self.botao_cortante.clicked.connect(self.abrir_janela_cortante)
        self.botao_momento.clicked.connect(self.abrir_janela_momento)
        self.botao_reacoes.clicked.connect(self.abrir_janela_reacoes)
        self.cancelar.clicked.connect(self.reject)
        self.confirmar.clicked.connect(self.acao_confirmar)

        self.radio_automatico.toggled.connect(self.alternar_modo_g1)
        self.radio_manual.toggled.connect(self.alternar_modo_g1)
        self.doubleSpinBox_g1.valueChanged.connect(self.atualizar_calculos_html)

        # Manual do usuário
        self.manual.clicked.connect(self.abrir_manual)

    def verificar_estados_iniciais(self):
        """Desabilita controles dependentes e ajusta disponibilidade da placa."""
        self.check_transversina.setChecked(False)
        self.toggle_transversina(False)
        self.radio_apoio.setChecked(True)

        self.check_elementos_extremidade.setChecked(False)
        self.toggle_extremidade(False)

        sup = self.gerenciador.get_superestrutura()
        if sup and sup.laje_transicao:
            self.spin_g_placa.setEnabled(True)
            self.label_g_placa.setEnabled(True)
        else:
            self.spin_g_placa.setEnabled(False)
            self.label_g_placa.setEnabled(False)

    # =========================================================================
    # Alternância entre modo automático e manual
    # =========================================================================
    def alternar_modo_g1(self, checked):
        """
        Gerencia a interface conforme o modo selecionado.
        O valor efetivo de g1 é calculado em atualizar_calculos_html.
        """
        if self.radio_automatico.isChecked():
            self.spin_gama_c.setEnabled(True)
            self.doubleSpinBox_g1.setEnabled(False)
            self.doubleSpinBox_g1.setSuffix("")
            self.doubleSpinBox_g1.clear()
            self.doubleSpinBox_g1.lineEdit().setPlaceholderText("")
            self.atualizar_calculos_html(ativo=True)
        else:
            self.spin_gama_c.setEnabled(False)
            self.doubleSpinBox_g1.setEnabled(True)
            self.doubleSpinBox_g1.setSuffix(" kN/m")

            if self.g1_valor_calculado > 0:
                self.doubleSpinBox_g1.setValue(self.g1_valor_calculado)
            else:
                self.atualizar_calculos_html(ativo=True)
                self.doubleSpinBox_g1.setValue(self.g1_valor_calculado)

            self.atualizar_calculos_html(ativo=False)

    def toggle_transversina(self, estado: bool):
        """Habilita/desabilita os controles de transversina."""
        self.radio_apoio.setEnabled(estado)
        self.radio_apoioevao.setEnabled(estado)
        self.label_transversina.setEnabled(estado)
        self.spin_p_transversina.setEnabled(estado)

    def toggle_extremidade(self, estado: bool):
        """Habilita/desabilita os controles de elementos de extremidade."""
        self.label_elemetos_extremidade.setEnabled(estado)
        self.label_p_elementos_extremidade.setEnabled(estado)
        self.spin_p_extremidade.setEnabled(estado)

    # =========================================================================
    # Desenho da seção transversal
    # =========================================================================
    def renderizar_desenho_secao(self):
        """Desenha a seção transversal completa no painel esquerdo."""
        sec = self.gerenciador.get_secao_transversal()
        sec_super = self.gerenciador.get_secao_superestrutura()

        if not sec or not sec_super:
            return

        area_longarina = sec_super.parametros_geometricos.get("Area Longarina", 0.0)

        if self.fig_secao:
            plt.close(self.fig_secao)
            self.fig_secao = None

        config_pers = None
        if sec.classe == "Personalizado":
            config_pers = sec.obter_config_via()

        self.fig_secao = desenhar_sec_transversal_completa(
            classe=sec.classe,
            h_borda=sec.h_borda,
            h_centro=sec.h_centro,
            n_longarinas=sec_super.n_longarinas,
            h_laje=sec_super.h_laje,
            d_extremidade=sec_super.d_extremidade,
            dados=sec_super.dados,
            passeio=sec.passeio,
            area_longarina=area_longarina,
            exibir_via=False,
            config_personalizado=config_pers
        )

        for i in reversed(range(self.layout_desenho.count())):
            self.layout_desenho.itemAt(i).widget().setParent(None)

        if self.fig_secao is not None:
            self.layout_desenho.addWidget(FigureCanvas(self.fig_secao))

    # =========================================================================
    # Cálculo e exibição do HTML da área e da carga g1
    # =========================================================================
    def atualizar_calculos_html(self, ativo=None):
        """
        Atualiza os painéis HTML com o memorial de cálculo da área e da carga g1.
        O valor efetivo de g1 é definido conforme o modo (automático ou manual).
        """
        sec_super = self.gerenciador.get_secao_superestrutura()
        if not sec_super:
            return

        if ativo is None:
            ativo = self.radio_automatico.isChecked()

        h_laje = sec_super.h_laje
        l_laje = sec_super.largura_total
        n_longarinas = sec_super.n_longarinas
        area_longarina = sec_super.parametros_geometricos.get("Area Longarina", 0.0)

        html_area = gerar_html_calculo_area(
            h_laje, l_laje, n_longarinas, area_longarina, ativo=ativo
        )
        self.html_calculo_area.setText(html_area)

        a_total_cm2 = (l_laje * h_laje) + (area_longarina * n_longarinas)
        a_total_m2 = a_total_cm2 / 10000.0
        gama_c = self.spin_gama_c.value()

        if ativo:
            self.g1_valor_calculado = (a_total_m2 * gama_c) / n_longarinas
        else:
            self.g1_valor_calculado = self.doubleSpinBox_g1.value()

        html_g1 = gerar_html_carga_g1(a_total_m2, gama_c, n_longarinas, ativo=ativo)
        self.html_carga_g1.setText(html_g1)

    # =========================================================================
    # Mapeamento da geometria e ações
    # =========================================================================
    def _obter_tipo_interno(self, texto_visual: str) -> str:
        """Converte o texto descritivo do tipo estrutural para chave interna."""
        for chave_visual, interno in MAPA_TIPOS.items():
            if chave_visual in texto_visual:
                return interno
        if "Múltiplos Vãos" in texto_visual:
            return "biapoiada"
        if "Biapoiada com Balanço" in texto_visual:
            return "isostatica_em_balanco"
        if "Vão Contínuo sem Balanço" in texto_visual:
            return "hiperestatica_sem_balanco"
        if "Vão Contínuo com Balanço" in texto_visual:
            return "hiperestatica_com_balanco"
        return "biapoiada"

    def mapear_coordenadas_estrutura(self, tipo_interno: str, vaos: list, laje_transicao: float):
        """
        Calcula as coordenadas dos apoios e meios de vãos para o desenho,
        retornando x_ini, x_fim, pontos_apoio e pontos_meio.
        """
        if tipo_interno in ['isostatica_em_balanco', 'hiperestatica_sem_balanco']:
            soma_vaos = vaos[0] + (2 * vaos[1])
        elif tipo_interno == 'hiperestatica_com_balanco':
            soma_vaos = vaos[0] + (2 * vaos[1]) + (2 * vaos[2])
        else:
            soma_vaos = sum(vaos)

        soma_lajes = (2 * laje_transicao) if laje_transicao else 0
        total_real = soma_vaos + soma_lajes
        fator = max(0.5, total_real / 20.0)
        gap_visual = (0.60 * fator) + (0.15 * fator)

        x_ini = laje_transicao if laje_transicao else 0.0
        x_cursor = x_ini

        pontos_apoio = []
        pontos_meio = []

        if tipo_interno == 'biapoiada':
            for vao in vaos:
                pontos_apoio.extend([x_cursor, x_cursor + vao])
                pontos_meio.append(x_cursor + (vao / 2.0))
                x_cursor += vao + gap_visual
            x_fim = x_cursor - gap_visual

        elif tipo_interno == 'isostatica_em_balanco':
            v_int, v_bal = vaos[0], vaos[1]
            p0 = x_ini
            p1 = p0 + v_bal
            p2 = p1 + v_int
            p3 = p2 + v_bal
            pontos_apoio.extend([p1, p2])
            pontos_meio.extend([p0 + v_bal/2, p1 + v_int/2, p2 + v_bal/2])
            x_fim = p3

        elif tipo_interno == 'hiperestatica_com_balanco':
            v_c, v_e, v_b = vaos[0], vaos[1], vaos[2]
            p0 = x_ini
            p1 = p0 + v_b
            p2 = p1 + v_e
            p3 = p2 + v_c
            p4 = p3 + v_e
            p5 = p4 + v_b
            pontos_apoio.extend([p1, p2, p3, p4])
            pontos_meio.extend([p0 + v_b/2, p1 + v_e/2, p2 + v_c/2, p3 + v_e/2, p4 + v_b/2])
            x_fim = p5

        else:  # hiperestatica_sem_balanco
            v_c, v_e = vaos[0], vaos[1]
            p0 = x_ini
            p1 = p0 + v_e
            p2 = p1 + v_c
            p3 = p2 + v_e
            pontos_apoio.extend([p0, p1, p2, p3])
            pontos_meio.extend([p0 + v_e/2, p1 + v_c/2, p2 + v_e/2])
            x_fim = p3

        return x_ini, x_fim, pontos_apoio, pontos_meio

    def montar_dicionario_acoes(self) -> dict:
        """
        Constrói o dicionário de ações (cargas concentradas e distribuídas)
        a partir dos dados atuais da interface.
        """
        sup = self.gerenciador.get_superestrutura()
        tipo_interno = self._obter_tipo_interno(sup.tipo)
        laje_transicao = float(sup.laje_transicao) if sup.laje_transicao else 0.0

        x_ini, x_fim, pts_apoio, pts_meio = self.mapear_coordenadas_estrutura(
            tipo_interno, sup.vaos, laje_transicao
        )

        acoes = {
            "Carga Concentrada": [],
            "Carga Distribuída": []
        }

        # Carga distribuída de peso próprio (g1 efetivo)
        acoes["Carga Distribuída"].append([round(self.g1_valor_calculado, 2), x_ini, x_fim])

        # Carga de placa de transição (se aplicável)
        if laje_transicao and self.spin_g_placa.isEnabled():
            g_placa = self.spin_g_placa.value()
            acoes["Carga Distribuída"].append([g_placa, 0.0, x_ini])
            acoes["Carga Distribuída"].append([g_placa, x_fim, x_fim + laje_transicao])

        # Elementos de extremidade
        if self.check_elementos_extremidade.isChecked():
            p_ext = self.spin_p_extremidade.value()
            acoes["Carga Concentrada"].append([p_ext, x_ini, x_fim])

        # Transversinas
        if self.check_transversina.isChecked():
            p_trans = self.spin_p_transversina.value()
            coords = list(pts_apoio)
            if self.radio_apoioevao.isChecked():
                coords.extend(pts_meio)
            coords = sorted(list(set(coords)))
            if coords:
                acoes["Carga Concentrada"].append([p_trans] + coords)

        return acoes

    # =========================================================================
    # Desenho da ponte carregada
    # =========================================================================
    def processar_desenho_ponte(self):
        """Gera o diagrama da ponte com as cargas atuais."""
        sup = self.gerenciador.get_superestrutura()
        if not sup:
            QMessageBox.warning(self, "Aviso", "A Superestrutura precisa estar definida.")
            return

        self.atualizar_calculos_html()

        tipo_interno = self._obter_tipo_interno(sup.tipo)
        laje_transicao = float(sup.laje_transicao) if sup.laje_transicao else 0.0
        acoes = self.montar_dicionario_acoes()

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
                acoes=acoes
            )
            self.layout_desenho_2.addWidget(FigureCanvas(self.fig_ponte))
        except Exception as e:
            QMessageBox.critical(self, "Erro de Renderização",
                                 f"Ocorreu um erro ao gerar o DCL da ponte:\n{str(e)}")

    # =========================================================================
    # Cálculo via MEF
    # =========================================================================
    def processar_calculos(self):
        """Executa a análise MEF, atualiza tabelas e gera diagramas."""
        sup = self.gerenciador.get_superestrutura()
        sec_sup = self.gerenciador.get_secao_superestrutura()

        if not sup or not sec_sup:
            QMessageBox.warning(self, "Aviso", "Superestrutura e Seção precisam estar definidos.")
            return

        self.atualizar_calculos_html()

        acoes = self.montar_dicionario_acoes()
        modulo_E_padrao = 3000.0  # kN/cm²

        try:
            self.calculadora = CalculadoraElementosFinitos(
                superestrutura=sup,
                secao_superestrutura=sec_sup,
                acoes=acoes,
                modulo_elasticidade=modulo_E_padrao
            )

            self.tabela_reacoes, self.tabela_cortante, self.tabela_momento = self.calculadora.calcular()

            # Fecha figuras anteriores
            if self.fig_cortante:
                plt.close(self.fig_cortante)
                self.fig_cortante = None
            if self.fig_momento:
                plt.close(self.fig_momento)
                self.fig_momento = None

            self.fig_cortante = self.calculadora.plotar_cortante()
            self.fig_momento = self.calculadora.plotar_momento()

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

            # Extrai valores extremos
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
            traceback.print_exc()
            QMessageBox.critical(self, "Erro no Cálculo",
                                 f"Falha na Análise MEF:\n{str(e)}\n\nConsulte o terminal para detalhes.")

    # =========================================================================
    # Abertura das janelas de resultados detalhados
    # =========================================================================
    def abrir_janela_cortante(self):
        """Exibe o diagrama e a tabela de esforço cortante."""
        if self.fig_cortante:
            plt.close(self.fig_cortante)
        self.fig_cortante = self.calculadora.plotar_cortante()

        valores_v = [float(linha[2]) for linha in self.tabela_cortante[1:]]
        v_min, v_max = min(valores_v), max(valores_v)

        janela = LogicaJanelaResultadosEsforcos(
            titulo_janela="Resumo do Esforço Cortante: Peso Próprio",
            titulo_diagrama="Diagrama de Esforço Cortante",
            titulo_tabela="Tabela Esforço Cortante",
            dados_tabela=self.tabela_cortante,
            figura_matplotlib=self.fig_cortante,
            valores_destaque=[v_min, v_max]
        )
        janela.exec()

    def abrir_janela_momento(self):
        """Exibe o diagrama e a tabela de momento fletor."""
        if self.fig_momento:
            plt.close(self.fig_momento)
        self.fig_momento = self.calculadora.plotar_momento()

        valores_m = [float(linha[2]) for linha in self.tabela_momento[1:]]
        m_min, m_max = min(valores_m), max(valores_m)

        janela = LogicaJanelaResultadosEsforcos(
            titulo_janela="Resumo do Momento Fletor: Peso Próprio",
            titulo_diagrama="Diagrama de Momento Fletor",
            titulo_tabela="Tabela Momento Fletor",
            dados_tabela=self.tabela_momento,
            figura_matplotlib=self.fig_momento,
            valores_destaque=[m_min, m_max]
        )
        janela.exec()

    def abrir_janela_reacoes(self):
        """Exibe a tabela de reações de apoio."""
        valores_r = [float(linha[2]) for linha in self.tabela_reacoes[1:]]
        r_max = max(valores_r)

        janela = LogicaJanelaResultadosReacoes(
            titulo_janela="Resumo das Reações de Apoio: Peso Próprio",
            dados_tabela=self.tabela_reacoes,
            valores_destaque=[r_max]
        )
        janela.exec()

    # =========================================================================
    # Salvamento dos dados
    # =========================================================================
    def acao_confirmar(self):
        """Salva os resultados de peso próprio no gerenciador e fecha o diálogo."""
        if not self.tabela_cortante or not self.tabela_momento or not self.tabela_reacoes:
            QMessageBox.warning(self, "Aviso", "Realize os cálculos antes de confirmar.")
            return

        self.gerenciador.definir_esforco(
            nome="peso_proprio",
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
        Abre o manual do software no PDFViewer na seção de análise das cargas
        de peso próprio (g1).

        Navega diretamente para a página 55 do manual (índice 55 em base 0,
        pois o PyMuPDF (fitz) indexa páginas a partir de zero).
        """
        pdf_path = resource_path(os.path.join("assets", "Manual Girder25 Dark.pdf"))
        viewer = PDFViewer(pdf_path, "Manual: ANÁLISE DAS CARGAS DE PESO PRÓPRIO (𝒈𝟏)")
        viewer.display_page(55)   # página 55 do manual → índice 55
        viewer.exec()